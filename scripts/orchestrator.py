#!/usr/bin/env python3
"""
orchestrator.py — host-side control plane for LLM Sched Copilot (Phase B).

Runs the full host-side pipeline end-to-end:

    workload selection
        -> workload_analyzer   (workload_summary.json)
        -> llm_advisor         (recommendation.json; STRICT by default. Opt-in to
                                 committed demo fixtures with --offline-fixture
                                 when running without UPSTAGE_API_KEY.)
        -> algorithm_guard     (guard_decision.json)
        -> execution backend   (simulator OR real xv6 under QEMU)
        -> export to dashboard_live live-data + rich manifest.json

Both backends are wired end-to-end:
  - simulator: scheduler_simulator.py writes trace_*.jsonl + metrics.json.
  - xv6: builds the kernel, boots QEMU, runs schedtest per algorithm (LLM-selected
    first), captures the serial console to outputs/xv6_raw_<algo>_seed<seed>.log,
    parses each via trace_parser.py (windowed to the run, ticks rebased), and
    aggregates metrics.json across the traces.

Usage:
    python3 scripts/orchestrator.py --backend simulator --seed 42 \\
        --workload interactive --run-all
    python3 scripts/orchestrator.py --backend xv6 --seed 42 \\
        --workload interactive --run-all
    python3 scripts/orchestrator.py --backend xv6 --algo mlfq --workload interactive
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
TOOLS_DIR = ROOT / "tools"
DEMO_DIR = ROOT / "outputs" / "_demo_fixtures"
OUTPUTS = ROOT / "outputs" / "live"
LIVE_DATA = ROOT / "dashboard_live" / "public" / "live-data"
XV6_DIR = ROOT / "xv6-riscv"
RAW_LOG_DIR = ROOT / "outputs"  # outputs/xv6_raw_<algo>_seed<seed>.log

# Make schema_compat helpers importable.
sys.path.insert(0, str(TOOLS_DIR))
from schema_compat import (  # noqa: E402
    CANONICAL_ALGOS,
    get_guard_algorithm,
    get_recommended_algorithm,
    normalize_algo,
    normalize_algorithm_name,
    normalize_target_metric,
)
from metrics import compute_metrics, param_application_status  # noqa: E402

ORCHESTRATOR_VERSION = "1.0.0"

# QEMU invocation (mirrors xv6-riscv/Makefile `qemu` target, CPUS=1).
QEMU_BIN = "qemu-system-riscv64"
QEMU_OPTS = [
    "-machine", "virt", "-bios", "none", "-kernel", "kernel/kernel",
    "-m", "128M", "-smp", "1", "-nographic",
    "-global", "virtio-mmio.force-legacy=false",
    "-drive", "file=fs.img,if=none,format=raw,id=x0",
    "-device", "virtio-blk-device,drive=x0,bus=virtio-mmio-bus.0",
]
# schedtest only knows these curated profiles; fall back to mixed otherwise.
XV6_PROFILES = {"interactive", "cpu_bound", "mixed", "priority_sensitive",
                "interactive_storm", "batch_convoy",
                # Larger discriminating profiles (feedback train/test set).
                "convoy_tail", "cpu_quad", "burst_storm", "prio_starve",
                "bimodal", "preempt_stream"}
QEMU_BOOT_WAIT = 4.0      # seconds to wait for the shell prompt before typing
QEMU_RUN_TIMEOUT = 60.0   # max seconds to wait for RUN_END before giving up

# Profile name -> workload file (the user chose: map to existing JSON, do NOT synthesize).
PROFILE_MAP = {
    # Legacy xv6 profile aliases (kept for backward compat with schedtest).
    "interactive":        ROOT / "workloads" / "interactive_heavy.json",
    "cpu_bound":          ROOT / "workloads" / "long_cpu_bound_first.json",
    "mixed":              ROOT / "workloads" / "mixed_workload.json",
    "priority_sensitive": ROOT / "workloads" / "priority_sensitive.json",
    # Larger curated xv6 profiles (8 procs). Their canonical file IS the mirror,
    # since for the xv6 backend the analyzed processes must equal the forked ones.
    "interactive_storm":  ROOT / "workloads" / "xv6_interactive_storm.json",
    "batch_convoy":       ROOT / "workloads" / "xv6_batch_convoy.json",
    # Larger discriminating xv6 profiles (feedback train/test set); their
    # canonical file IS the mirror (xv6 analyzes exactly what it forks).
    "convoy_tail":        ROOT / "workloads" / "xv6_convoy_tail.json",
    "cpu_quad":           ROOT / "workloads" / "xv6_cpu_quad.json",
    "burst_storm":        ROOT / "workloads" / "xv6_burst_storm.json",
    "prio_starve":        ROOT / "workloads" / "xv6_prio_starve.json",
    "bimodal":            ROOT / "workloads" / "xv6_bimodal.json",
    "preempt_stream":     ROOT / "workloads" / "xv6_preempt_stream.json",
    "short_jobs":         ROOT / "workloads" / "short_jobs.json",
    "starvation_risk":    ROOT / "workloads" / "starvation_risk.json",
    # v2 workload IDs (matches the `id` field in each workload JSON;
    # see docs/workload_coverage_matrix.md). Simulator backend only — xv6
    # schedtest still uses the legacy 4 curated profiles.
    "interactive_heavy":      ROOT / "workloads" / "interactive_heavy.json",
    "short_jobs_clustered":   ROOT / "workloads" / "short_jobs.json",
    "long_job_first_convoy":  ROOT / "workloads" / "long_cpu_bound_first.json",
    "interactive_mixed":      ROOT / "workloads" / "mixed_workload.json",
    "priority_critical_tasks":ROOT / "workloads" / "priority_sensitive.json",
    "cpu_bound_vs_io_bound":  ROOT / "workloads" / "cpu_bound_vs_io_bound.json",
    "ambiguous_mixed":        ROOT / "workloads" / "ambiguous_mixed.json",
    "pure_batch":             ROOT / "workloads" / "pure_batch.json",
    "bursty_long_tail":       ROOT / "workloads" / "bursty_long_tail.json",
    # Scheduling-lab coverage workloads (simulator only; each isolates one
    # canonical scheduling phenomenon — see docs/workload_coverage_matrix.md).
    "convoy_effect":            ROOT / "workloads" / "convoy_effect.json",
    "fairness_rr":              ROOT / "workloads" / "fairness_rr.json",
    "staggered_short_arrival":  ROOT / "workloads" / "staggered_short_arrival.json",
    "starvation_priority":      ROOT / "workloads" / "starvation_priority.json",
    "burst_prediction_demo":    ROOT / "workloads" / "burst_prediction_demo.json",
}

# For the xv6 backend, the LLM pipeline must analyze the EXACT processes that
# schedtest forks, so burst priors align by fork index.  Each curated xv6
# profile maps to a mirror workload JSON whose process order == the schedtest.c
# WORKLOADS table order.  Used only when backend == xv6.
XV6_MIRROR_MAP = {
    "interactive":        ROOT / "workloads" / "xv6_interactive.json",
    "cpu_bound":          ROOT / "workloads" / "xv6_cpu_bound.json",
    "mixed":              ROOT / "workloads" / "xv6_mixed.json",
    "priority_sensitive": ROOT / "workloads" / "xv6_priority_sensitive.json",
    "interactive_storm":  ROOT / "workloads" / "xv6_interactive_storm.json",
    "batch_convoy":       ROOT / "workloads" / "xv6_batch_convoy.json",
    "convoy_tail":        ROOT / "workloads" / "xv6_convoy_tail.json",
    "cpu_quad":           ROOT / "workloads" / "xv6_cpu_quad.json",
    "burst_storm":        ROOT / "workloads" / "xv6_burst_storm.json",
    "prio_starve":        ROOT / "workloads" / "xv6_prio_starve.json",
    "bimodal":            ROOT / "workloads" / "xv6_bimodal.json",
    "preempt_stream":     ROOT / "workloads" / "xv6_preempt_stream.json",
}

# Trace files written by the simulator (lowercase canonical names).
TRACE_ALGOS = [a.lower() for a in CANONICAL_ALGOS]

META_FILES = (
    "recommendation.json",
    "guard_decision.json",
    "workload_summary.json",
    "trace_explanation.json",
)


# ── helpers (reused from the old pipeline) ─────────────────────────────────────

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def copy_file(src: Path, dst: Path, dry_run: bool = False):
    if not src.exists():
        print(f"  [WARN] missing: {src}")
        return
    print(f"  copy  {_rel(src)} -> {_rel(dst)}")
    if not dry_run:
        shutil.copy2(src, dst)


def write_json(path: Path, data: dict, dry_run: bool = False):
    print(f"  write {_rel(path)}")
    if not dry_run:
        path.write_text(json.dumps(data, indent=2))


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return {}


def _parse_feedback_rules(path: Path) -> list[str]:
    """Count usable bullet rules in a feedback_rules.md file.

    Mirrors llm_advisor.parse_rules_from_markdown's contract loosely (bullet
    lines, skipping the 'none' sentinel) so the manifest's feedback_rule_count
    matches what the advisor would actually inject. Returns [] on any error.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return []
    rules: list[str] = []
    for raw in text.splitlines():
        stripped = raw.lstrip()
        for marker in ("- ", "* "):
            if stripped.startswith(marker):
                rule = stripped[len(marker):].strip()
                if rule and rule.lower() not in {"none", "n/a", "(none)"}:
                    rules.append(rule)
                break
    return rules


def _run(cmd: list[str], dry_run: bool) -> int:
    print(f"  cmd: {' '.join(cmd)}")
    if dry_run:
        print("  [DRY-RUN] skipped")
        return 0
    return subprocess.run(cmd, capture_output=False).returncode


# ── workload resolution ────────────────────────────────────────────────────────

def resolve_workload(profile: str) -> tuple[str, Path]:
    """Resolve a profile name (or direct .json path) to (workload_type, file).

    Direct paths ending in .json are used as-is and the workload_type becomes
    the file stem. Otherwise the name must be a known profile.
    """
    if profile.endswith(".json"):
        path = Path(profile)
        if not path.is_absolute():
            path = (ROOT / path).resolve()
        if not path.is_file():
            sys.exit(f"[orchestrator] workload file not found: {path}")
        return path.stem, path

    if profile not in PROFILE_MAP:
        known = ", ".join(sorted(PROFILE_MAP))
        sys.exit(
            f"[orchestrator] unknown workload profile: {profile!r}. "
            f"Known profiles: {known}. (Or pass a path ending in .json.)"
        )

    path = PROFILE_MAP[profile]
    if not path.is_file():
        sys.exit(
            f"[orchestrator] profile {profile!r} maps to a missing file: {path}"
        )
    return profile, path


# ── pipeline steps (before running) ────────────────────────────────────────────

def run_workload_analyzer(workload: Path, out_dir: Path, dry_run: bool):
    """Run workload_analyzer and ensure output lands at <out_dir>/workload_summary.json.

    The analyzer hardcodes its output to outputs/workload_summary.json, so we
    run it then copy the result into out_dir.
    """
    print("\n[1] Workload analyzer")
    cmd = [sys.executable, str(TOOLS_DIR / "workload_analyzer.py"), str(workload)]
    rc = _run(cmd, dry_run)
    if rc != 0:
        print(f"  [WARN] workload_analyzer exited {rc}")
    target = out_dir / "workload_summary.json"
    analyzer_out = ROOT / "outputs" / "workload_summary.json"
    if not dry_run:
        if analyzer_out.exists() and analyzer_out.resolve() != target.resolve():
            copy_file(analyzer_out, target, dry_run)
        elif not target.exists():
            print("  [WARN] workload_summary.json not produced; demo fallback used later")


def run_advisor(out_dir: Path, dry_run: bool, *, offline_fixture: bool = False,
                use_feedback: bool = False) -> bool:
    """Run llm_advisor (advise).

    Default behavior is STRICT: if the advisor fails (missing UPSTAGE_API_KEY,
    network error, schema error, etc.) the orchestrator exits with a clear
    error so we never silently fake a real Solar Pro 3 call. To use the
    committed demo recommendation as a fixture, pass --offline-fixture.

    Feedback consumption is OPT-IN (use_feedback=True). When enabled, the
    accumulated FAIL-only rules at `out_dir/feedback_rules.md` (the canonical
    orchestrator path, written by step [9] of a PRIOR run) are injected into
    the advise prompt. Default runs pass NO --feedback argument, so stale rules
    cannot influence the recommendation and the demo stays deterministic. The
    feedback file is generated AFTER evaluation, so it never affects this run.

    Returns True if the demo fallback was used (caller flags metadata_source).
    """
    print("\n[2] LLM advisor")
    summary = out_dir / "workload_summary.json"
    rec_out = out_dir / "recommendation.json"
    cmd = [
        sys.executable, str(TOOLS_DIR / "llm_advisor.py"),
        "--mode", "advise",
        "--in", str(summary),
        "--out", str(rec_out),
    ]
    if use_feedback:
        feedback_file = out_dir / "feedback_rules.md"
        cmd.extend(["--feedback", str(feedback_file)])
        if feedback_file.is_file():
            n = len(_parse_feedback_rules(feedback_file))
            print(f"  --use-feedback ON: injecting {n} accumulated rule(s) "
                  f"from {_rel(feedback_file)}")
        else:
            print(f"  --use-feedback ON: no rules file at {_rel(feedback_file)} "
                  f"yet; advising with base prompt (no crash).")
    if dry_run:
        print(f"  cmd: {' '.join(cmd)}")
        print("  [DRY-RUN] skipped")
        return False

    ok = False
    try:
        rc = subprocess.run(cmd, capture_output=False).returncode
        ok = rc == 0 and rec_out.exists()
        if not ok:
            print(f"  [advisor] exited {rc}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [advisor] exception: {exc}")
        ok = False

    if ok:
        return False

    if not offline_fixture:
        sys.exit(
            "[orchestrator] LLM advisor failed (most often: UPSTAGE_API_KEY "
            "missing or network error). The orchestrator will not silently "
            "substitute a fake Solar Pro 3 response.\n"
            "  Fix options:\n"
            "    1) Put a real key in .env  (cp .env.example .env, then edit)\n"
            "    2) Re-run with --offline-fixture to explicitly use the committed\n"
            "       outputs/_demo_fixtures/ fixtures and stamp metadata_source=demo_fallback."
        )

    print("[advisor] --offline-fixture set -> using committed demo recommendation")
    demo_rec = DEMO_DIR / "recommendation.json"
    if not demo_rec.exists():
        sys.exit(f"[orchestrator] demo recommendation fallback missing: {demo_rec}")
    copy_file(demo_rec, rec_out, dry_run)
    return True


def run_guard(out_dir: Path, dry_run: bool, *, offline_fixture: bool = False) -> bool:
    """Run algorithm_guard.

    Default behavior is STRICT: if the guard process fails the orchestrator
    exits with a clear error. To use the committed demo guard_decision as a
    fixture, pass --offline-fixture.

    Returns True if the demo fallback was used (caller flags metadata_source).
    """
    print("\n[3] Algorithm guard")
    rec_in = out_dir / "recommendation.json"
    guard_out = out_dir / "guard_decision.json"
    cmd = [
        sys.executable, str(TOOLS_DIR / "algorithm_guard.py"),
        "--in", str(rec_in),
        "--out", str(guard_out),
    ]
    if dry_run:
        print(f"  cmd: {' '.join(cmd)}")
        print("  [DRY-RUN] skipped")
        return False

    ok = False
    fellback = False
    try:
        rc = subprocess.run(cmd, capture_output=False).returncode
        ok = rc == 0 and guard_out.exists()
        if not ok:
            print(f"  [guard] exited {rc}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [guard] exception: {exc}")
        ok = False

    if not ok:
        if not offline_fixture:
            sys.exit(
                "[orchestrator] algorithm_guard failed and --offline-fixture "
                "was not set. Re-run with --offline-fixture to use the committed "
                "outputs/_demo_fixtures/guard_decision.json fixture, or fix the underlying "
                "guard error."
            )
        print("[guard] --offline-fixture set -> using committed demo guard_decision")
        demo_guard = DEMO_DIR / "guard_decision.json"
        if not demo_guard.exists():
            sys.exit(f"[orchestrator] demo guard fallback missing: {demo_guard}")
        copy_file(demo_guard, guard_out, dry_run)
        fellback = True

    # Safety net: algorithm_guard.py now emits a DISPLAY-form `scheduling_algorithm`
    # itself. Only fill it in if somehow missing (e.g. an older demo file), keeping
    # the canonical display spelling so the dashboard reads it consistently.
    guard = _read_json(guard_out)
    if guard and not guard.get("scheduling_algorithm"):
        algo = normalize_algorithm_name(get_guard_algorithm(guard, default="RR"))
        guard["scheduling_algorithm"] = algo
        guard_out.write_text(json.dumps(guard, indent=2) + "\n")
        print(f"  [guard] filled missing scheduling_algorithm={algo}")
    return fellback


def resolve_selected_algorithm(out_dir: Path) -> str:
    """Resolve the LLM-selected algorithm: guard decision first, then recommendation."""
    guard = _read_json(out_dir / "guard_decision.json")
    rec = _read_json(out_dir / "recommendation.json")
    has_guard_algo = bool((guard or {}).get("scheduling_algorithm")
                          or (guard or {}).get("algorithm"))
    if has_guard_algo:
        return get_guard_algorithm(guard, default="RR")
    has_rec_algo = bool((rec or {}).get("recommended_scheduling_algorithm")
                        or (rec or {}).get("algorithm"))
    if has_rec_algo:
        return get_recommended_algorithm(rec, default="RR")
    return normalize_algo("RR")


def compute_run_order(selected: str) -> list[str]:
    """LLM-selected first, then the rest in canonical order."""
    selected = normalize_algo(selected)
    rest = [a for a in CANONICAL_ALGOS if a != selected]
    return [selected] + rest


# ── execution backends (running) ───────────────────────────────────────────────

def run_simulator_backend(workload: Path, out_dir: Path, dry_run: bool) -> bool:
    """Run the host-side simulator on the workload + guard decision.

    The simulator runs ALL 6 algorithms on the SAME workload and writes
    trace_<algo>.jsonl for each plus metrics.json (with comparison, judgment,
    regret_score). No separate trace_parser / metrics step is needed here.
    """
    print("\n[4] Execution backend: simulator")
    guard_file = out_dir / "guard_decision.json"
    cmd = [
        sys.executable, str(TOOLS_DIR / "scheduler_simulator.py"),
        "--workload", str(workload),
        "--guard", str(guard_file),
        "--out-dir", str(out_dir),
    ]
    rc = _run(cmd, dry_run)
    if rc != 0:
        print(f"  [ERROR] simulator exited {rc}")
        return False
    return True


def _load_jsonl(path: Path) -> list[dict]:
    evs: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                evs.append(json.loads(line))
            except Exception:  # noqa: BLE001
                pass
    return evs


def ensure_xv6_built(dry_run: bool) -> bool:
    """Build the kernel and fs.img (CPUS=1) if missing/stale.

    The default `make` target only builds the kernel, so fs.img (which compiles
    the user programs, including schedtest) is built explicitly.
    """
    print("\n[xv6] Building kernel + fs.img (CPUS=1)")
    if dry_run:
        print("  [DRY-RUN] skipped")
        return True
    for target in (["CPUS=1"], ["fs.img", "CPUS=1"]):
        rc = subprocess.run(["make", *target], cwd=str(XV6_DIR),
                            capture_output=True, text=True).returncode
        if rc != 0:
            print(f"  [ERROR] make {' '.join(target)} failed (rc={rc})")
            return False
    ok = (XV6_DIR / "kernel" / "kernel").exists() and (XV6_DIR / "fs.img").exists()
    print("  build OK" if ok else "  [ERROR] kernel/fs.img missing after build")
    return ok


def qemu_run_schedtest(algo_lower: str, seed: int, profile: str, raw_path: Path,
                       dry_run: bool, pred_args: list[str] | None = None) -> bool:
    """Boot xv6 under QEMU, run one schedtest, capture the console to raw_path.

    Waits for the shell, types `schedtest <algo> <seed> <profile> [pred_args...]`,
    then waits for the RUN_END marker (or a timeout) and quits QEMU via Ctrl-A x.
    `pred_args` carries the Guard-validated predictor params + per-process burst
    priors (SJF/SRTF only); they are appended verbatim to the command line.
    Returns True if a RUN_END for this run was captured.
    """
    cmd = f"schedtest {algo_lower} {seed} {profile}"
    if pred_args:
        cmd += " " + " ".join(pred_args)
    print(f"  [qemu] {cmd}  -> {_rel(raw_path)}")
    if dry_run:
        print("  [DRY-RUN] skipped")
        return True

    proc = subprocess.Popen(
        [QEMU_BIN, *QEMU_OPTS], cwd=str(XV6_DIR),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    lines: list[str] = []
    done = threading.Event()

    def reader():
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
            if "event=RUN_END" in line:
                done.set()
                break

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    try:
        time.sleep(QEMU_BOOT_WAIT)
        if proc.stdin:
            proc.stdin.write(cmd + "\n")
            proc.stdin.flush()
        done.wait(timeout=QEMU_RUN_TIMEOUT)
        time.sleep(0.5)
        try:
            if proc.stdin:
                proc.stdin.write("\x01x")  # Ctrl-A x quits QEMU (-nographic)
                proc.stdin.flush()
        except Exception:  # noqa: BLE001
            pass
    finally:
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            proc.kill()

    raw_path.write_text("".join(lines))
    ok = any("event=RUN_END" in ln for ln in lines)
    if not ok:
        print(f"  [WARN] no RUN_END captured for {algo_lower} (timeout?)")
    return ok


def _extract_run_window(raw_path: Path, algo: str | None = None) -> str:
    """Return only the lines between RUN_BEGIN and RUN_END (inclusive).

    Be lenient: kernel printf occasionally interleaves with the user-space
    `[SCHEDTEST] event=RUN_BEGIN ...` line and splits it mid-print. We have
    observed two failure modes:
      1. The `[SCHEDTEST] event` prefix is shorn off, leaving `=RUN_BEGIN ...`.
         Matching the bare `RUN_BEGIN` substring recovers this case.
      2. The `RUN_BEGIN` word itself is truncated (e.g. `event=RUN_BEGI[SCHED]
         tick=... algo=RR event=PREEMPT ...`). The first attempt above misses
         this; we fall back to anchoring on the first line that names the
         target algorithm — `algo=<target>` — which is always emitted by the
         kernel once the run has switched.

         **RR-specific guard:** the kernel boots with RR as the default
         scheduler, so it emits `algo=RR` lines from very early in boot
         (init/sh dispatches). To prevent the fallback from anchoring on
         those boot lines we additionally require that a `[SCHEDTEST]`
         marker has been observed first — that guarantees the schedtest
         userspace program is actually running. This closes a real bug:
         the snapshot generated in PR #38 picked up ~32 boot-time
         `pid=1`/`pid=2` DISPATCH events that inflated RR's
         avg_response_time on the `interactive` profile to 34.2.
    RUN_END is robust enough by itself (we have not seen it mid-print).
    """
    raw_text = raw_path.read_text()
    lines = raw_text.splitlines()

    def _window(predicate) -> list[str]:
        out: list[str] = []
        in_win = False
        for ln in lines:
            if not in_win and predicate(ln):
                in_win = True
            if in_win:
                out.append(ln)
            if "RUN_END" in ln:
                break
        return out

    result = _window(lambda ln: "RUN_BEGIN" in ln)
    if not result and algo:
        target = f"algo={algo.upper()}"
        # Two-stage predicate: require a [SCHEDTEST] marker AT OR BEFORE
        # the target match. We track whether [SCHEDTEST] has been seen in
        # the line stream so far.
        out: list[str] = []
        in_win = False
        schedtest_seen = False
        for ln in lines:
            if "[SCHEDTEST]" in ln:
                schedtest_seen = True
            if not in_win and schedtest_seen and target in ln:
                in_win = True
            if in_win:
                out.append(ln)
            if "RUN_END" in ln:
                break
        result = out
    return "\n".join(result) + "\n"


def parse_xv6_log(raw_path: Path, algo: str, seed: int, profile: str,
                  out_dir: Path, dry_run: bool, trace_name: str | None = None) -> bool:
    """Window the raw log to the run, parse to trace_<algo>.jsonl, then force the
    algo label and rebase ticks so the run starts at t=0 (children fork together,
    so a 0-based clock yields correct relative response/turnaround/waiting).

    `trace_name` overrides the output file name (e.g. trace_mlfq_corrected.jsonl
    for the runtime-correction apply loop)."""
    trace_out = out_dir / (trace_name or f"trace_{algo.lower()}.jsonl")
    if dry_run:
        print(f"  [DRY-RUN] parse {_rel(raw_path)} -> {_rel(trace_out)}")
        return True

    window = _extract_run_window(raw_path, algo=algo)
    with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as tf:
        tf.write(window)
        win_path = Path(tf.name)

    rc = subprocess.run(
        [sys.executable, str(TOOLS_DIR / "trace_parser.py"),
         "--input", str(win_path), "--algo", algo,
         "--seed", str(seed), "--profile", profile,
         "--out", str(trace_out)],
        capture_output=True, text=True,
    ).returncode
    win_path.unlink(missing_ok=True)
    if rc != 0 or not trace_out.exists():
        print(f"  [ERROR] trace_parser failed for {algo} (rc={rc})")
        return False

    # Force algo label (the RR->target transition leaves a few RR-labelled
    # dispatches) and rebase ticks to the window start.
    evs = _load_jsonl(trace_out)
    ints = [e["tick"] for e in evs if isinstance(e.get("tick"), int)]
    base = min(ints) if ints else 0
    for e in evs:
        e["algo"] = algo
        if isinstance(e.get("tick"), int):
            e["tick"] = e["tick"] - base

    # PROC_DEF.arrival is schedtest's planned arrival (relative to its own
    # t0 = uptime() before any fork), but DISPATCH ticks come from the
    # kernel's uptime counter. After rebasing to the first DISPATCH tick,
    # timer-granularity drift between schedtest's t0 and the kernel's
    # first scheduling decision can leave PROC_DEF.arrival off by one
    # tick — which surfaces downstream as response_time = first_run -
    # arrival < 0 in metrics.py. The kernel's observation is authoritative:
    # if a process was actually DISPATCHed at tick fd, it MUST have been
    # RUNNABLE by tick fd, so its real arrival is <= fd. Snap arrival down
    # to fd when the planned value contradicts the trace.
    first_dispatch: dict[int, int] = {}
    for e in evs:
        if (e.get("event") == "DISPATCH"
                and isinstance(e.get("pid"), int)
                and isinstance(e.get("tick"), int)
                and e["pid"] not in first_dispatch):
            first_dispatch[e["pid"]] = e["tick"]
    for e in evs:
        if e.get("event") != "PROC_DEF":
            continue
        pid = e.get("pid")
        arr = e.get("arrival")
        fd = first_dispatch.get(pid) if isinstance(pid, int) else None
        if fd is not None and isinstance(arr, int) and fd < arr:
            e["arrival"] = fd

    trace_out.write_text("".join(json.dumps(e) + "\n" for e in evs))
    return True


def _metric_key(target: str | None) -> tuple[str, bool]:
    """Map a target metric name to (metrics-key, lower_is_better)."""
    t = (target or "").lower()
    if "wait" in t:
        return "avg_waiting_time", True
    if "turn" in t:
        return "avg_turnaround_time", True
    if "through" in t:
        return "throughput", False
    return "avg_response_time", True


def build_xv6_metrics(out_dir: Path, selected: str, run_order: list[str],
                      guard_params: dict, target_metric: str | None,
                      dry_run: bool, pred_args: list[str] | None = None) -> bool:
    """Aggregate per-algorithm xv6 traces into a metrics.json with a comparison
    block, matching the schema the dashboard already consumes."""
    print("\n[xv6] Aggregating metrics across traces")
    if dry_run:
        print("  [DRY-RUN] skipped")
        return True

    full: dict[str, dict] = {}
    comparison: dict[str, dict] = {}
    for algo in run_order:
        tp = out_dir / f"trace_{algo.lower()}.jsonl"
        if not tp.exists():
            continue
        m = compute_metrics(_load_jsonl(tp))
        if not m:
            print(f"  [WARN] no metrics for {algo} (no EXIT events)")
            continue
        disp = normalize_algorithm_name(algo)
        full[disp] = m
        applied = m.get("applied_params", {})
        comparison[disp] = {
            "avg_waiting_time":      m["avg_waiting_time"],
            "avg_response_time":     m["avg_response_time"],
            "avg_turnaround_time":   m["avg_turnaround_time"],
            "throughput":            m["throughput"],
            "max_waiting_time":      m["max_waiting_time"],
            "preemption_count":      m["preemption_count"],
            "starvation_occurred":   m["starvation_occurred"],
            "burst_prediction_error": None,
            "judgment":              None,
            # Per-algorithm honesty: what xv6 ACTUALLY applied for this algo,
            # read from this run's own trace (*_PARAMS events when the dynamic
            # param reached the kernel = source llm_guard; kernel defaults =
            # source xv6_default; {} for FCFS). recommended_params is filled in
            # below only for the LLM-selected algorithm (the Guard validates
            # params for the selection, not every comparison run).
            "applied_params":        applied,
            "recommended_params":    {},
            "param_application_status": param_application_status(disp, applied),
        }

    if not comparison:
        print("  [ERROR] no usable traces to build metrics")
        return False

    mkey, lower_better = _metric_key(target_metric)
    vals = [c[mkey] for c in comparison.values() if isinstance(c.get(mkey), (int, float))]
    best = (min(vals) if lower_better else max(vals)) if vals else 0.0
    # Absolute tick noise floor for the regret denominator. xv6 traces are tick-
    # granular and very short, so when best≈0 a relative-only delta blows up:
    # FCFS at avg_response_time=0.2 vs MLFQ=0.0 isn't a meaningful regression,
    # it's sub-tick rounding. JUDGMENT_ABS_FLOOR clamps the denominator and
    # also short-circuits SUCCESS when the absolute gap fits inside it. On
    # simulator traces where waits run into the tens, this floor is dwarfed
    # by `abs(best)` and has no effect.
    JUDGMENT_ABS_FLOOR = 0.5

    def _judge(c: dict) -> tuple[str, float]:
        # Canonical thresholds; starvation forces FAIL.
        if c.get("starvation_occurred"):
            return "FAIL", 1.0
        v = c.get(mkey)
        if not isinstance(v, (int, float)):
            return "UNKNOWN", 0.0
        # Sub-tick noise: gaps smaller than the absolute floor are SUCCESS.
        if "through" not in mkey and abs(v - best) <= JUDGMENT_ABS_FLOOR:
            return "SUCCESS", 0.0
        denom = max(abs(best), JUDGMENT_ABS_FLOOR)
        delta = round((best - v) / denom if not lower_better else (v - best) / denom, 3)
        # Single source of truth: tools/metrics.py constants.
        from metrics import SUCCESS_REGRET, NEAR_SUCCESS_REGRET
        if delta <= SUCCESS_REGRET:
            return "SUCCESS", delta
        if delta <= NEAR_SUCCESS_REGRET:
            return "NEAR-SUCCESS", delta
        return "FAIL", delta

    for c in comparison.values():
        c["judgment"], _ = _judge(c)

    selected = normalize_algorithm_name(selected)
    if selected not in full:
        selected = next(iter(full))
    top = dict(full[selected])
    top["scheduling_algorithm"] = selected
    # Honesty split (see docs): `recommended_params` is what the LLM/Guard asked
    # for; `applied_params` (already derived by tools/metrics.derive_applied_params
    # from this run's own trace) is what xv6 actually used. `params` is kept as a
    # legacy mirror of the recommendation so the existing dashboard keeps working.
    top["params"] = guard_params or {}
    top["recommended_params"] = guard_params or {}
    top.setdefault("applied_params", {})

    # Authoritative applied_params for the SELECTED algorithm. The dynamic
    # RR/Priority/MLFQ params and the SJF/SRTF predictor params/priors genuinely
    # reach the kernel (the matching *_PARAMS / BURST_HINT_APPLIED trace events
    # confirm acceptance). Their serial lines can be truncated by interleaved
    # kernel prints, so we record the values authoritatively from the exact
    # Guard-validated tokens the orchestrator passed on the command line. This
    # stays honest: every value here was actually sent to and accepted by xv6.
    ema, hints = _parse_pred_flags(pred_args)
    authoritative = _applied_from_guard(selected, guard_params or {}, ema, hints)
    if authoritative:
        top["applied_params"] = authoritative

    # Keep the selected algorithm's comparison entry consistent with the
    # authoritative top-level applied_params, fill its recommended_params, and
    # recompute its status (it now reflects llm_guard application).
    if selected in comparison:
        comparison[selected]["applied_params"] = top["applied_params"]
        comparison[selected]["recommended_params"] = guard_params or {}
        comparison[selected]["param_application_status"] = param_application_status(
            selected, top["applied_params"]
        )
    top["recommended_params"] = guard_params or {}
    top["param_application_status"] = param_application_status(
        selected, top["applied_params"]
    )
    top["comparison"] = comparison
    top["judgment"], top["regret_score"] = _judge(comparison[selected])
    top.setdefault("starvation_pids", [])

    # Populate the v2 evaluation fields the dashboard's Evaluation tab needs.
    # These are intentionally derived in the orchestrator (not tools/metrics.evaluate_run)
    # because the orchestrator owns the cross-algorithm comparison object.
    mkey = (
        "throughput" if "through" in (target_metric or "").lower()
        else (target_metric or "avg_response_time")
    )
    # Find the algorithm with the best value on the target metric.
    candidates = [
        (algo, c.get(mkey))
        for algo, c in comparison.items()
        if isinstance(c.get(mkey), (int, float))
    ]
    best_algo = None
    best_val = None
    if candidates:
        chooser = max if "through" in mkey.lower() else min
        best_algo, best_val = chooser(candidates, key=lambda x: x[1])
    sel_val = comparison.get(selected, {}).get(mkey)

    top["target_metric"] = mkey
    top["selected_metric_value"] = sel_val
    top["best_algorithm"] = best_algo
    top["best_metric_value"] = best_val
    # One-line explanation matching tools/metrics._explain_judgment.
    if top.get("starvation_occurred"):
        top["explanation"] = (
            f"FAIL: {selected} caused starvation"
            + (f" on pid(s) {top.get('starvation_pids')}" if top.get('starvation_pids') else "")
            + " — starvation forces FAIL regardless of regret."
        )
    elif top["regret_score"] is None or sel_val is None or best_val is None or best_algo is None:
        top["explanation"] = f"UNKNOWN: insufficient comparison data for {selected} on {mkey}."
    else:
        raw_pct = top["regret_score"] * 100
        if raw_pct >= 999.5:
            pct_str, tail = ">999%", " (regret huge because best≈0)"
        else:
            pct_str, tail = f"{round(raw_pct, 1)}%", ""
        verdict = top["judgment"]
        bound = ("(<= 10%)" if verdict == "SUCCESS"
                 else "(10-25%)" if verdict == "NEAR-SUCCESS" else "(> 25%)")
        top["explanation"] = (
            f"{verdict}: {selected} on {mkey} = {sel_val} vs "
            f"best ({best_algo}) = {best_val}; regret = {pct_str} {bound}.{tail}"
        )

    (out_dir / "metrics.json").write_text(json.dumps(top, indent=2))
    print(f"  metrics.json: selected={selected} judgment={top['judgment']} "
          f"regret={top['regret_score']}")
    return True


def _build_predictor_args(out_dir: Path, mirror_path: Path | None) -> list[str] | None:
    """Build schedtest predictor CLI FLAGS for SJF/SRTF from the guard decision.

    Flag layout (consumed by user/schedtest.c):
        --alpha A --initial I --min M --max X --hints h0,h1,...
    where alpha..max come from guard_decision.params (the Guard-validated
    predictor parameters) and the hints are per-process initial burst priors
    aligned to the mirror workload's process order == schedtest fork order.
    Returns None if no usable priors are available (schedtest then uses kernel
    defaults).

    The priors are LLM estimates derived from VISIBLE features only; the true
    future bursts (actual_bursts) are never read here.
    """
    guard = _read_json(out_dir / "guard_decision.json") or {}

    # Per-process priors are produced by the LLM independently of which algorithm
    # was finally selected, so the SJF/SRTF comparison runs can use them even
    # when the LLM picked a different algorithm. If there are none, fall back to
    # the kernel's built-in predictor (no args).
    pb_list = guard.get("predicted_bursts") or []
    by_pid = {it.get("pid"): it for it in pb_list if isinstance(it, dict)}
    if not by_pid:
        return None

    # Predictor params land in guard_decision.params only when SJF/SRTF was the
    # selected algorithm; otherwise reuse the predictor defaults (mirror of
    # proc.c struct predictor_params {50, 10, 1, 100}).
    params = guard.get("params") or {}
    try:
        alpha = int(params["alpha_percent"])
        initial = int(params["initial"])
        min_b = int(params["min"])
        max_b = int(params["max"])
    except (KeyError, TypeError, ValueError):
        alpha, initial, min_b, max_b = 50, 10, 1, 100

    # Per-process priors aligned to fork order via the mirror workload.
    mirror = _read_json(mirror_path) if mirror_path else None
    procs = (mirror or {}).get("processes") or []
    hints: list[int] = []
    for p in procs:
        entry = by_pid.get(p.get("pid"))
        pb = entry.get("predicted_burst") if isinstance(entry, dict) else None
        if not isinstance(pb, int) or pb < 1:
            pb = initial  # no LLM prior for this process -> predictor initial
        hints.append(pb)

    tokens = ["--alpha", str(alpha), "--initial", str(initial),
              "--min", str(min_b), "--max", str(max_b)]
    if hints:
        tokens += ["--hints", ",".join(str(h) for h in hints)]
    return tokens


def _parse_pred_flags(args: list[str] | None) -> tuple[dict, list[int]]:
    """Parse predictor flag tokens -> (ema_params, burst_hints).

    Pure inverse of the --alpha/--initial/--min/--max/--hints flags built by
    _build_predictor_args, so build_xv6_metrics can record the exact values
    sent to (and accepted by) xv6. Returns ({}, []) when no predictor args.
    """
    if not args:
        return {}, []
    ema: dict = {}
    hints: list[int] = []
    keymap = {"--alpha": "alpha_percent", "--initial": "initial",
              "--min": "min", "--max": "max"}
    i = 0
    while i < len(args):
        tok = args[i]
        if tok in keymap and i + 1 < len(args):
            try:
                ema[keymap[tok]] = int(args[i + 1])
            except ValueError:
                pass
            i += 2
        elif tok == "--hints" and i + 1 < len(args):
            hints = [int(x) for x in args[i + 1].split(",")
                     if x.strip().lstrip("-").isdigit()]
            i += 2
        else:
            i += 1
    return ema, hints


def _mlfq_flags(params: dict) -> list[str] | None:
    """Build --mlfq-* flags from Guard MLFQ params, or None if unusable."""
    queues = params.get("queues")
    quantum = params.get("quantum")
    boost = params.get("boost_interval")
    if not isinstance(queues, int) or not isinstance(quantum, list) or not quantum:
        return None
    q = [int(x) for x in quantum if isinstance(x, (int, float)) and not isinstance(x, bool)]
    q = q[:5]
    if not q:
        return None
    flags = ["--mlfq-queues", str(queues), "--mlfq-quantum", ",".join(str(x) for x in q)]
    if isinstance(boost, int):
        flags += ["--mlfq-boost", str(boost)]
    return flags


def _schedtest_flags_for(algo: str, selected: str, guard_params: dict,
                         pred_args: list[str] | None) -> list[str] | None:
    """Per-algorithm schedtest CLI flags.

    SJF/SRTF always receive the predictor flags (the LLM produces burst priors
    independently of which algorithm was finally selected). RR/Priority/MLFQ
    receive their dynamic params ONLY when they are the LLM-selected algorithm —
    the Guard validates params for the selection, not for every comparison run,
    so non-selected RR/Priority/MLFQ runs honestly use kernel defaults.
    """
    au = algo.upper()
    if au in ("SJF", "SRTF"):
        return pred_args
    if au != selected.upper():
        return None
    if au == "RR":
        q = guard_params.get("quantum")
        if isinstance(q, int):
            return ["--rr-quantum", str(q)]
    elif au == "PRIORITY":
        t = guard_params.get("aging_threshold")
        if isinstance(t, int):
            return ["--aging", str(t)]
    elif au == "MLFQ":
        return _mlfq_flags(guard_params)
    return None


def _applied_from_guard(algo: str, guard_params: dict,
                        ema: dict, hints: list[int]) -> dict | None:
    """Authoritative applied_params for the SELECTED algo, from the exact values
    the orchestrator passed to schedtest (the *_PARAMS trace event confirms the
    kernel accepted them; this survives serial-line truncation). Returns None
    when the algorithm applies no dynamic params."""
    au = algo.upper()
    if au == "RR":
        q = guard_params.get("quantum")
        if isinstance(q, int):
            return {"quantum": q, "source": "llm_guard"}
    elif au == "PRIORITY":
        t = guard_params.get("aging_threshold")
        if isinstance(t, int):
            return {"aging_threshold": t, "priority_source": "schedtest_profile",
                    "source": "llm_guard"}
    elif au == "MLFQ":
        flags = _mlfq_flags(guard_params)
        if flags:
            ap = {"source": "llm_guard", "queues": guard_params.get("queues")}
            quantum = [int(x) for x in guard_params.get("quantum", [])
                       if isinstance(x, (int, float)) and not isinstance(x, bool)][:5]
            ap["quantum"] = quantum
            if isinstance(guard_params.get("boost_interval"), int):
                ap["boost_interval"] = guard_params["boost_interval"]
            return ap
    elif au in ("SJF", "SRTF"):
        # The EMA params only come from the Guard when SJF/SRTF was the selected
        # algorithm (guard_params then carries alpha_percent). Otherwise
        # _build_predictor_args fell back to the kernel predictor defaults
        # {50,10,1,100}; labelling those "llm_guard" would be dishonest. The
        # per-process burst_hints, when present, are genuine LLM priors either way.
        guard_supplied = "alpha_percent" in (guard_params or {})
        ap = {"source": "llm_guard" if guard_supplied else "xv6_default"}
        ap.update(ema)
        if hints:
            ap["burst_hints"] = hints
            ap["burst_hints_source"] = "llm_guard"
        return ap
    return None


def run_xv6_backend(out_dir: Path, seed: int, profile: str, run_order: list[str],
                    algo: str | None, dry_run: bool) -> bool:
    """Execute the workload on the real xv6 kernel under QEMU and parse the result.

    Steps: build -> for each algorithm, boot QEMU + run schedtest + capture the
    serial console -> window to the run -> parse to trace_<algo>.jsonl -> aggregate
    metrics.json. The LLM-selected algorithm runs first.
    """
    print("\n[4] Execution backend: xv6")

    xv6_profile = profile if profile in XV6_PROFILES else "mixed"
    if xv6_profile != profile:
        print(f"  [note] profile {profile!r} has no curated xv6 table; using {xv6_profile!r}")

    algos = [normalize_algo(algo)] if algo else list(run_order)
    print(f"  algorithms (selected first): {algos}")

    if not ensure_xv6_built(dry_run):
        return False

    # Predictor params + per-process burst priors for SJF/SRTF, built once from
    # the guard decision and the curated mirror workload (fork-order aligned).
    mirror_path = XV6_MIRROR_MAP.get(xv6_profile)
    pred_args = _build_predictor_args(out_dir, mirror_path)
    if pred_args:
        print(f"  predictor args (SJF/SRTF): {' '.join(pred_args)}")

    # Dynamic RR/Priority/MLFQ params reach xv6 only for the LLM-selected algo
    # (Guard validates params for the selection). Built from guard_decision.
    guard = _read_json(out_dir / "guard_decision.json") or {}
    guard_params = guard.get("params") or {}
    selected_upper = algos[0].upper()

    parsed_any = False
    for a in algos:
        raw_path = RAW_LOG_DIR / f"xv6_raw_{a.lower()}_seed{seed}.log"
        a_args = _schedtest_flags_for(a, selected_upper, guard_params, pred_args)
        if a_args and a.upper() == selected_upper:
            print(f"  schedtest flags ({a}): {' '.join(a_args)}")
        if not qemu_run_schedtest(a.lower(), seed, xv6_profile, raw_path, dry_run, a_args):
            print(f"  [WARN] capture failed for {a}; skipping")
            continue
        if parse_xv6_log(raw_path, a, seed, xv6_profile, out_dir, dry_run):
            parsed_any = True

    if not parsed_any and not dry_run:
        print("  [ERROR] no xv6 traces were captured/parsed")
        return False

    guard = _read_json(out_dir / "guard_decision.json")
    rec = _read_json(out_dir / "recommendation.json")
    guard_params = (guard or {}).get("params", {})
    target_metric = (rec or {}).get("target_metric") or "avg_response_time"
    selected = algos[0]
    return build_xv6_metrics(out_dir, selected, algos, guard_params,
                             target_metric, dry_run, pred_args=pred_args)


# ── after-running LLM stages (trace explanation + feedback rules) ──────────────

def run_trace_explainer(out_dir: Path, live_dir: Path, selected: str, *,
                        offline_fixture: bool, dry_run: bool) -> None:
    """[8] Trace Explainer — natural-language explanation of the finished run.

    Always produces a FRESH trace_explanation.json for THIS run or an explicit
    non-stale `available: false` placeholder. Never leaves an older run's
    explanation in place. Uses the real Solar Pro 3 LLM when a key is available;
    with --offline-fixture and no key it falls back to the committed demo
    explanation (stamped source=demo_fallback); otherwise writes the placeholder.
    """
    print("\n[8] Trace explainer (after-running LLM)")
    exp_out = out_dir / "trace_explanation.json"
    live_exp = live_dir / "trace_explanation.json"
    trace = out_dir / f"trace_{selected.lower()}.jsonl"
    metrics = out_dir / "metrics.json"
    rec = out_dir / "recommendation.json"
    proposal = out_dir / "correction_proposal.json"

    if dry_run:
        print("  [DRY-RUN] skipped")
        return

    # Never leave a stale explanation from a previous run.
    for p in (exp_out, live_exp):
        try:
            p.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass

    sel_disp = normalize_algorithm_name(selected)

    def _placeholder(reason: str, source: str = "not_available") -> None:
        doc = {
            "available": False,
            "reason": reason,
            "generated_at": _iso_now(),
            "source": source,
            "scheduling_algorithm": sel_disp,
        }
        exp_out.write_text(json.dumps(doc, indent=2) + "\n")
        copy_file(exp_out, live_exp, False)
        print(f"  trace_explanation: unavailable ({source})")

    if not (trace.is_file() and metrics.is_file()):
        _placeholder("no trace/metrics available to explain for this run")
        return

    cmd = [
        sys.executable, str(TOOLS_DIR / "trace_explainer.py"),
        "--trace", str(trace), "--metrics", str(metrics),
        "--out", str(exp_out),
    ]
    if rec.is_file():
        cmd += ["--rec", str(rec)]
    if proposal.is_file():
        cmd += ["--proposal", str(proposal)]

    ok = False
    try:
        rc = subprocess.run(cmd, capture_output=False).returncode
        ok = rc == 0 and exp_out.exists()
    except Exception as exc:  # noqa: BLE001
        print(f"  [explainer] exception: {exc}")
        ok = False

    if ok:
        doc = _read_json(exp_out)
        doc["available"] = True
        doc.setdefault("source", "llm")
        doc["scheduling_algorithm"] = doc.get("scheduling_algorithm") or sel_disp
        doc["generated_at"] = _iso_now()
        exp_out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        copy_file(exp_out, live_exp, False)
        print(f"  trace_explanation: fresh (source={doc.get('source')})")
        return

    # LLM failed (most often: UPSTAGE_API_KEY missing or network error).
    if offline_fixture:
        demo = DEMO_DIR / "trace_explanation.json"
        if demo.is_file():
            doc = _read_json(demo)
            doc["available"] = True
            doc["source"] = "demo_fallback"
            doc["scheduling_algorithm"] = doc.get("scheduling_algorithm") or sel_disp
            doc["generated_at"] = _iso_now()
            exp_out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
            copy_file(exp_out, live_exp, False)
            print("  trace_explanation: committed demo fixture (offline-fixture)")
            return
    _placeholder(
        "trace explanation was not generated for this run "
        "(LLM unavailable: no UPSTAGE_API_KEY or network error)"
    )


def run_feedback_generator(out_dir: Path, live_dir: Path, *,
                           offline_fixture: bool, dry_run: bool) -> None:
    """[9] Feedback Rule Generator — FAIL-only prompt-feedback loop.

    Per CLAUDE.md, the feedback loop fires ONLY on a FAIL judgment (or
    starvation). SUCCESS / NEAR-SUCCESS skip honestly and leave the rules
    untouched. Feedback is NEVER faked: if the LLM is unavailable (no key),
    we log an explicit skip rather than substituting a fixture — even in
    --offline-fixture mode. Rules generated here affect FUTURE recommendations,
    not the just-finished run.
    """
    print("\n[9] Feedback rule generator (FAIL-only)")
    metrics = out_dir / "metrics.json"
    rec = out_dir / "recommendation.json"
    rules_out = out_dir / "feedback_rules.md"
    live_rules = live_dir / "feedback_rules.md"

    if dry_run:
        print("  [DRY-RUN] skipped")
        return

    m = _read_json(metrics)
    judgment = str(m.get("judgment", "")).strip().upper()
    starvation = bool(m.get("starvation_occurred"))

    if judgment != "FAIL" and not starvation:
        print(f"  feedback skipped honestly (judgment={judgment or 'UNKNOWN'}; "
              f"feedback fires only on FAIL).")
        return

    # Preserve any existing accumulated rules so the advisor's FIFO/dedup logic
    # sees them (it reads the --feedback file as both prior rules and output).
    if live_rules.is_file() and not rules_out.is_file():
        try:
            shutil.copy2(live_rules, rules_out)
        except Exception:  # noqa: BLE001
            pass

    cmd = [
        sys.executable, str(TOOLS_DIR / "llm_advisor.py"),
        "--mode", "feedback",
        "--metrics", str(metrics),
        "--rec", str(rec),
        "--feedback", str(rules_out),
    ]
    rc = 1
    try:
        rc = subprocess.run(cmd, capture_output=False).returncode
    except Exception as exc:  # noqa: BLE001
        print(f"  [feedback] exception: {exc}")
        rc = 1

    if rc != 0:
        # run_feedback raised SystemExit — the LLM was unavailable (missing
        # UPSTAGE_API_KEY or a network/API error). Feedback is NEVER faked, so
        # we honestly skip rather than substituting fixture rules (even with
        # --offline-fixture). The just-finished run is unaffected either way.
        suffix = " (offline-fixture set, but feedback is never faked)" if offline_fixture else ""
        print("  feedback skipped: LLM unavailable for feedback "
              "(missing UPSTAGE_API_KEY or network/API error)" + suffix)
        return

    # rc == 0: the advisor's feedback mode ran. It writes the rules file only
    # when the LLM produced NEW, non-duplicate rules; "no usable rules" / "only
    # duplicates" leave it untouched. Report which actually happened.
    if rules_out.is_file() and rules_out.read_text().strip():
        copy_file(rules_out, live_rules, False)
        print(f"  feedback rules written/updated -> {_rel(live_rules)}")
    else:
        print("  feedback ran on the FAIL run but produced no new rules "
              "(empty/duplicate); rules file unchanged.")


# ── metadata + export (after running) ──────────────────────────────────────────

def _stamp_fixture_provenance(target: Path, fixture: Path) -> None:
    """Mark a JSON file that was backfilled from a demo fixture so it can never
    masquerade as this run's own output. Best-effort: non-JSON or unreadable
    files are left untouched (the [meta] log line already flagged the fallback)."""
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return
    if isinstance(data, dict):
        data["metadata_source"] = "demo_fallback"
        data["_provenance"] = {
            "source": "demo_fixture_fallback",
            "note": "This file was missing for this run and was backfilled from "
                    "a committed demo fixture. It does NOT reflect this run.",
            "fixture": str(fixture),
        }
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")


def ensure_metadata_files(out_dir: Path, dry_run: bool):
    """Safety net: copy any missing metadata file from outputs/_demo_fixtures.

    Backfilled files are stamped with metadata_source=demo_fallback so a missing
    metadata file can never be silently presented as this run's real output.
    Measured results (metrics.json / trace_*.jsonl) are intentionally NOT in
    META_FILES, so they can never be backfilled this way."""
    for fname in META_FILES:
        target = out_dir / fname
        if not target.exists():
            src = DEMO_DIR / fname
            if src.exists():
                print(f"  [meta] using demo fallback for {fname} "
                      f"(stamped metadata_source=demo_fallback)")
                if not dry_run:
                    shutil.copy2(src, target)
                    _stamp_fixture_provenance(target, src)
            else:
                print(f"  [WARN] no source for {fname}")


def _judge_value(value, best, lower_better: bool) -> tuple[str, float | None]:
    """Judge a single metric value against the best, mirroring build_xv6_metrics."""
    from metrics import SUCCESS_REGRET, NEAR_SUCCESS_REGRET
    if not isinstance(value, (int, float)) or not isinstance(best, (int, float)):
        return "UNKNOWN", None
    FLOOR = 0.5
    if abs(value - best) <= FLOOR:
        return "SUCCESS", 0.0
    denom = max(abs(best), FLOOR)
    delta = round((value - best) / denom if lower_better else (best - value) / denom, 3)
    if delta <= SUCCESS_REGRET:
        return "SUCCESS", delta
    if delta <= NEAR_SUCCESS_REGRET:
        return "NEAR-SUCCESS", delta
    return "FAIL", delta


def _run_proposal_pipeline(out_dir: Path, live_dir: Path, selected_algo: str) -> tuple[dict, dict | None]:
    """event_detector -> correction_proposer -> correction_guard.

    Produces the OBSERVATIONAL runtime_events.json and the preview-only
    correction_proposal.json / correction_guard_decision.json (these remain
    preview_only=true: they are *proposals*; the apply happens downstream and is
    recorded separately in correction_applied.json). Returns (events_doc,
    guard_decision|None).
    """
    rec = live_dir / "recommendation.json"
    metrics = live_dir / "metrics.json"
    trace = live_dir / f"trace_{selected_algo.lower()}.jsonl"
    events_out = out_dir / "runtime_events.json"
    proposal_out = out_dir / "correction_proposal.json"
    decision_out = out_dir / "correction_guard_decision.json"
    for p in (events_out, proposal_out, decision_out,
              live_dir / "runtime_events.json",
              live_dir / "correction_proposal.json",
              live_dir / "correction_guard_decision.json"):
        try:
            p.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass

    if not (rec.is_file() and metrics.is_file() and trace.is_file()):
        return {}, None

    subprocess.run(
        [sys.executable, str(TOOLS_DIR / "event_detector.py"),
         "--trace", str(trace), "--metrics", str(metrics), "--out", str(events_out)],
        capture_output=False,
    )
    events_doc = _read_json(events_out) if events_out.is_file() else {}
    if events_out.is_file():
        copy_file(events_out, live_dir / "runtime_events.json", False)
    if not (isinstance(events_doc, dict) and events_doc.get("events")):
        return events_doc or {}, None

    subprocess.run(
        [sys.executable, str(TOOLS_DIR / "correction_proposer.py"),
         "--events", str(events_out), "--recommendation", str(rec),
         "--out", str(proposal_out)],
        capture_output=False,
    )
    if proposal_out.is_file():
        copy_file(proposal_out, live_dir / "correction_proposal.json", False)
        subprocess.run(
            [sys.executable, str(TOOLS_DIR / "correction_guard.py"),
             "--proposal", str(proposal_out), "--out", str(decision_out)],
            capture_output=False,
        )
        if decision_out.is_file():
            copy_file(decision_out, live_dir / "correction_guard_decision.json", False)
    return events_doc, (_read_json(decision_out) if decision_out.is_file() else None)


def _run_correction_apply_loop(out_dir: Path, live_dir: Path, *, backend: str,
                               seed: int, xv6_profile: str, mirror_path: Path | None,
                               selected: str, target_metric: str | None,
                               top_metrics: dict, guard_params: dict,
                               force_correction: str | None, dry_run: bool) -> None:
    """Guarded post-evaluation correction APPLY loop (host-side closed loop).

    Pipeline: initial recommendation -> guard -> xv6 execution -> metrics ->
    event detection -> correction proposal -> correction guard -> (if the
    recommendation FAILed and a better, guard-approved algorithm exists)
    re-run xv6 on the SAME mirror workload with the corrected algorithm/params,
    then compare before/after and record correction_applied.json (applied=true).

    This is NOT kernel hot-path LLM control: the LLM never runs in the kernel and
    never picks the next process. The correction is decided on the host AFTER a
    full run and applied by launching a second, ordinary xv6 run.
    """
    print("\n[7] Runtime correction apply loop (host-side closed loop)")
    applied_out = out_dir / "correction_applied.json"
    live_applied = live_dir / "correction_applied.json"

    def _publish(doc: dict) -> None:
        applied_out.write_text(json.dumps(doc, indent=2) + "\n")
        copy_file(applied_out, live_applied, False)

    if dry_run:
        return

    # Drop any stale corrected traces from a previous run so the published
    # live-data never carries an orphan trace_*_corrected.jsonl when this run
    # applies no correction.
    for stale in list(out_dir.glob("trace_*_corrected.jsonl")) + \
            list(live_dir.glob("trace_*_corrected.jsonl")):
        try:
            stale.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass

    # Always run the observational + proposal pipeline first (writes
    # runtime_events.json + preview proposal/guard for the dashboard).
    events_doc, _guard_dec = _run_proposal_pipeline(out_dir, live_dir, selected)
    high_sev = any(e.get("severity") == "high"
                   for e in (events_doc.get("events") or [])
                   if isinstance(e, dict))

    comparison = top_metrics.get("comparison") or {}
    mkey, lower_better = _metric_key(target_metric)
    judgment = top_metrics.get("judgment")
    best_algo = top_metrics.get("best_algorithm")

    # Trigger: the recommendation clearly underperformed (FAIL or starvation),
    # OR a high-severity runtime event was detected. --force-correction <ALGO>
    # forces the apply path for verification (stamped forced=true, honest about
    # the real original judgment).
    forced = bool(force_correction)
    should_correct = forced or judgment == "FAIL" or top_metrics.get("starvation_occurred") or high_sev

    if backend != "xv6":
        _publish({"applied": False,
                  "reason": "correction apply loop re-runs the real xv6 kernel; "
                            "not applicable to the simulator backend."})
        print("  applied=false (simulator backend)")
        return

    if not should_correct:
        _publish({"applied": False,
                  "reason": "Initial recommendation met success criteria "
                            f"(judgment={judgment}).",
                  "original_algorithm": selected,
                  "original_judgment": judgment,
                  "target_metric": mkey})
        print(f"  applied=false (judgment={judgment}; no correction warranted)")
        return

    # Choose the corrected algorithm: the best performer in the comparison
    # (the natural correction) unless forced to a specific one.
    corrected_algo = normalize_algorithm_name(force_correction) if forced else best_algo
    if not corrected_algo or normalize_algorithm_name(corrected_algo) == normalize_algorithm_name(selected):
        _publish({"applied": False,
                  "reason": f"No better guard-approved algorithm than {selected} "
                            "in the comparison; nothing to apply.",
                  "original_algorithm": selected,
                  "original_judgment": judgment,
                  "target_metric": mkey})
        print(f"  applied=false (no better algorithm than {selected})")
        return
    corrected_algo = normalize_algorithm_name(corrected_algo)

    # Corrected params: reproduce the EXACT configuration that made this
    # algorithm the best performer in the comparison. Non-selected comparison
    # runs use kernel defaults — _schedtest_flags_for returns None for any algo
    # that was not the LLM selection — so the correction MUST re-run with kernel
    # defaults too. Passing tuned "safe defaults" here (e.g. RR quantum=10 from
    # DEFAULT_PARAMS) would re-run a DIFFERENT configuration than the one that
    # actually won (xv6 RR baseline quantum=1) and could never confirm the
    # improvement — the re-run would just reproduce the FAIL it was correcting.
    try:
        from correction_guard import validate as cg_validate  # type: ignore
    except ImportError:
        sys.path.insert(0, str(TOOLS_DIR))
        from correction_guard import validate as cg_validate  # type: ignore
    corrected_params: dict = {}  # kernel baseline — matches the comparison winner

    # Re-validate the correction with the Correction Guard before applying.
    proposal = {
        "preview_only": True, "applied": False,
        "current_scheduling_algorithm": selected,
        "proposed": {
            "correction_type": "algorithm_change",
            "new_scheduling_algorithm": corrected_algo,
            "new_params": corrected_params,
            "rationale": f"{selected} judged {judgment} on {mkey}; "
                         f"{corrected_algo} was the best performer — re-run to confirm.",
        },
    }
    decision = cg_validate(proposal)
    if decision.get("guard_result") != "accepted":
        _publish({"applied": False,
                  "reason": f"Correction guard rejected the {corrected_algo} correction: "
                            f"{decision.get('reason')}",
                  "original_algorithm": selected,
                  "original_judgment": judgment,
                  "target_metric": mkey})
        print(f"  applied=false (correction guard rejected {corrected_algo})")
        return

    # APPLY: re-run xv6 with the corrected algorithm + params on the same workload.
    print(f"  applying correction: {selected} -> {corrected_algo} (re-running xv6)")
    au = corrected_algo.upper()
    if au in ("SJF", "SRTF"):
        flags = _build_predictor_args(out_dir, mirror_path)
    else:
        flags = _schedtest_flags_for(corrected_algo, corrected_algo, corrected_params, None)
    raw = RAW_LOG_DIR / f"xv6_raw_{au.lower()}_corrected_seed{seed}.log"
    trace_name = f"trace_{au.lower()}_corrected.jsonl"
    if not qemu_run_schedtest(au.lower(), seed, xv6_profile, raw, dry_run, flags):
        _publish({"applied": False,
                  "reason": f"corrected {corrected_algo} run failed to capture in xv6.",
                  "original_algorithm": selected, "corrected_algorithm": corrected_algo,
                  "original_judgment": judgment, "target_metric": mkey})
        print("  applied=false (corrected run capture failed)")
        return
    parse_xv6_log(raw, corrected_algo, seed, xv6_profile, out_dir, dry_run, trace_name)
    corrected_trace = out_dir / trace_name
    cm = compute_metrics(_load_jsonl(corrected_trace)) if corrected_trace.is_file() else None
    if not cm:
        _publish({"applied": False,
                  "reason": f"corrected {corrected_algo} run produced no metrics.",
                  "original_algorithm": selected, "corrected_algorithm": corrected_algo,
                  "original_judgment": judgment, "target_metric": mkey})
        print("  applied=false (corrected run no metrics)")
        return
    copy_file(corrected_trace, live_dir / trace_name, False)

    # Before/after comparison on the target metric (best = original best value).
    orig_val = comparison.get(selected, {}).get(mkey)
    corr_val = cm.get(mkey)
    best_vals = [c.get(mkey) for c in comparison.values() if isinstance(c.get(mkey), (int, float))]
    best_val = (min(best_vals) if lower_better else max(best_vals)) if best_vals else corr_val
    if isinstance(corr_val, (int, float)) and isinstance(best_val, (int, float)):
        best_val = min(best_val, corr_val) if lower_better else max(best_val, corr_val)
    corr_judgment, corr_regret = _judge_value(corr_val, best_val, lower_better)

    doc = {
        "applied": True,
        "mode": "post_evaluation_correction",
        "trigger": "forced" if forced else ("starvation" if top_metrics.get("starvation_occurred")
                                            else "fail_judgment" if judgment == "FAIL"
                                            else "high_severity_event"),
        "original_algorithm": selected,
        "corrected_algorithm": corrected_algo,
        "original_params": guard_params or {},
        "corrected_params": corrected_params,
        "corrected_config": "kernel_baseline",  # reproduces the comparison winner
        "original_judgment": judgment,
        "corrected_judgment": corr_judgment,
        "target_metric": mkey,
        "original_metric_value": orig_val,
        "corrected_metric_value": corr_val,
        "improved": (isinstance(orig_val, (int, float)) and isinstance(corr_val, (int, float))
                     and (corr_val < orig_val if lower_better else corr_val > orig_val)),
        "reason": proposal["proposed"]["rationale"],
        "trace_file": trace_name,
    }
    if forced:
        doc["forced"] = True
        doc["note"] = ("correction forced for apply-path verification; original "
                       "judgment is reported unchanged.")
    _publish(doc)
    print(f"  applied=true: {selected} ({orig_val}) -> {corrected_algo} ({corr_val}) "
          f"on {mkey}; corrected_judgment={corr_judgment}")


def export_to_live_data(out_dir: Path, live_dir: Path, *, backend: str, seed: int,
                        workload_type: str, workload_stem: str, selected: str,
                        run_order: list[str], dry_run: bool,
                        metadata_source: str | None = None,
                        feedback_consumed: bool = False,
                        feedback_rule_count: int = 0) -> dict:
    print(f"\n[5] Export to {_rel(live_dir)}")
    ensure_dir(live_dir)

    for algo in TRACE_ALGOS:
        copy_file(out_dir / f"trace_{algo}.jsonl", live_dir / f"trace_{algo}.jsonl", dry_run)

    copy_file(out_dir / "metrics.json", live_dir / "metrics.json", dry_run)
    for fname in META_FILES:
        copy_file(out_dir / fname, live_dir / fname, dry_run)

    # Burst-prediction ablation evidence (tools/burst_ablation.py). Static
    # across runs — regenerated by the ablation tool, not the pipeline — so we
    # only mirror it when it already exists; the dashboard card hides itself
    # when absent. This surfaces the LLM's measured contribution in the demo.
    ablation_src = ROOT / "outputs" / "ablation" / "burst_ablation.json"
    if ablation_src.is_file():
        copy_file(ablation_src, live_dir / "burst_ablation.json", dry_run)

    # target_metric from recommendation, else default — canonical form
    rec = _read_json(out_dir / "recommendation.json")
    target = normalize_target_metric(rec.get("target_metric")) if rec.get("target_metric") else "avg_response_time"

    # version increment from existing manifest
    existing = _read_json(live_dir / "manifest.json")
    version = int(existing.get("version", 0)) + 1

    now = _iso_now()
    mode = "simulator" if backend == "simulator" else "xv6-log"

    # DISPLAY-form algorithm names for the dashboard.
    selected_disp = normalize_algorithm_name(selected)
    order_disp = [normalize_algorithm_name(a) for a in run_order]

    manifest = {
        # ── new (additive) fields ──
        "backend": backend,
        "seed": seed,
        "workload_type": workload_type,
        "llm_selected_algorithm": selected_disp,
        "algorithms_executed": order_disp,
        "generated_at": now,
        "orchestrator_version": ORCHESTRATOR_VERSION,
        # ── legacy mirrors (keep the current dashboard working) ──
        "mode": mode,
        "updated_at": now,
        "version": version,
        "workload": workload_stem,
        "algorithms": order_disp,
        "recommended_algorithm": selected_disp,
        "target_metric": target,
    }
    # Honest provenance: flag when metadata came from the demo fallback.
    if metadata_source:
        manifest["metadata_source"] = metadata_source

    # Feedback CONSUMPTION provenance (compact, dashboard-contract-compatible).
    # Distinct from feedback GENERATION (step [9], post-evaluation). Only stamp
    # the verbose fields when feedback was actually opted into.
    manifest["feedback_consumed"] = bool(feedback_consumed)
    if feedback_consumed:
        manifest["feedback_rules_path"] = "outputs/live/feedback_rules.md"
        manifest["feedback_rule_count"] = int(feedback_rule_count)

    write_json(live_dir / "manifest.json", manifest, dry_run)
    print(f"  manifest version -> {version}"
          + (f"  (metadata_source={metadata_source})" if metadata_source else ""))
    return manifest


# ── main ────────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(
        description="LLM Sched Copilot — host-side Orchestrator (Phase B)"
    )
    p.add_argument("--backend", choices=["xv6", "simulator"], default="simulator")
    p.add_argument("--mode", choices=["simulator", "xv6-log", "xv6", "fallback"],
                   default=None,
                   help="legacy alias for --backend (simulator | xv6-log/xv6 -> xv6 | fallback)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--workload", default="interactive",
                   help="profile name or path ending in .json")
    p.add_argument("--run-all", action="store_true",
                   help="run all algorithms (default for simulator)")
    p.add_argument("--algo", default=None,
                   help="single-algo override (mainly for xv6 later)")
    p.add_argument("--out-dir", default=str(OUTPUTS))
    p.add_argument("--live-data-dir", default=str(LIVE_DATA))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--offline-fixture",
        dest="offline_fixture",
        action="store_true",
        help=(
            "Opt in to using committed outputs/_demo_fixtures/ fixtures when the LLM "
            "advisor or algorithm guard fails (e.g. no UPSTAGE_API_KEY, "
            "network down). Default is STRICT: failures exit with a clear "
            "error so we never silently fake a Solar Pro 3 call. When set, "
            "manifest.metadata_source is stamped 'demo_fallback'."
        ),
    )
    # Back-compat synonym for callers that already use --allow-fallback.
    p.add_argument(
        "--allow-fallback",
        dest="offline_fixture",
        action="store_true",
        help="Alias for --offline-fixture.",
    )
    p.add_argument(
        "--use-feedback",
        dest="use_feedback",
        action="store_true",
        help=(
            "OPT-IN: inject accumulated FAIL-only feedback rules from "
            "outputs/live/feedback_rules.md into the advise prompt. Default is "
            "OFF so the demo stays deterministic and stale/overfit rules cannot "
            "pollute the recommendation. Rules are still GENERATED after a FAIL "
            "regardless of this flag — this flag only controls CONSUMPTION."
        ),
    )
    p.add_argument(
        "--force-correction",
        dest="force_correction",
        default=None,
        help="(xv6 verification aid) force the post-evaluation correction apply "
        "loop to correct to this algorithm regardless of judgment, so the apply "
        "path can be exercised end-to-end. The artifact is stamped forced=true "
        "and reports the real original judgment unchanged.",
    )
    args = p.parse_args()

    # Legacy --mode alias maps onto --backend (xv6-log/xv6 -> xv6, else simulator).
    if args.mode:
        args.backend = "xv6" if args.mode in ("xv6-log", "xv6") else "simulator"

    out_dir = Path(args.out_dir)
    live_dir = Path(args.live_data_dir)
    dry_run = args.dry_run

    workload_type, workload_path = resolve_workload(args.workload)

    # xv6 backend: schedtest only runs the curated profiles, so collapse the
    # requested workload to one of them and analyze its MIRROR JSON instead of
    # the original v2 workload. This keeps the LLM burst priors aligned to the
    # exact processes xv6 forks (process order == fork order). The simulator
    # backend keeps using the full v2 workload unchanged.
    if args.backend == "xv6":
        xv6_profile = workload_type if workload_type in XV6_PROFILES else "mixed"
        mirror = XV6_MIRROR_MAP.get(xv6_profile)
        if mirror and mirror.is_file():
            if xv6_profile != workload_type or workload_path != mirror:
                print(f"[orchestrator] xv6 backend: analyzing mirror workload "
                      f"{_rel(mirror)} for profile {xv6_profile!r}")
            workload_type, workload_path = xv6_profile, mirror
        else:
            # No mirror on disk: the analyzer would read the ORIGINAL workload
            # while run_xv6_backend collapses execution to 'mixed' — a silent
            # divergence (burst priors misaligned to the forked processes). All
            # XV6_PROFILES ship a mirror, so this only fires if a profile was
            # added without one. Fail loud rather than diverge quietly.
            print(f"[orchestrator] WARNING: no mirror JSON for xv6 profile "
                  f"{xv6_profile!r} (looked up {XV6_MIRROR_MAP.get(xv6_profile)}); "
                  f"analyzer will read {_rel(workload_path)} but xv6 executes "
                  f"'mixed' — burst priors may be misaligned. Add a mirror JSON.")

    workload_stem = workload_path.stem

    # Simulator backend: make --seed MEANINGFUL. Materialise a seed-jittered
    # INSTANCE of the workload (arrival/burst magnitudes vary; process count and
    # per-process burst/io counts preserved) and analyse + simulate THAT, so
    # different seeds give genuinely different runs (multi-seed statistics) and
    # the dashboard's "random" option produces fresh data each press. xv6 stays
    # deterministic-by-profile: its curated schedtest.c tables are fixed in C
    # with no PRNG, so we never jitter the kernel path.
    if args.backend == "simulator" and not dry_run:
        instance_path = out_dir / "workload_instance.json"
        rc = _run([sys.executable, str(TOOLS_DIR / "workload_jitter.py"),
                   "--in", str(workload_path), "--out", str(instance_path),
                   "--seed", str(args.seed)], dry_run)
        if rc == 0 and instance_path.is_file():
            print(f"[orchestrator] simulator: seed {args.seed} -> jittered "
                  f"instance {_rel(instance_path)}")
            workload_path = instance_path
        else:
            print(f"  [WARN] jitter failed (rc={rc}); using base workload unchanged")

    print("=" * 64)
    print("LLM Sched Copilot — Orchestrator")
    print(f"  backend     : {args.backend}")
    print(f"  seed        : {args.seed}")
    print(f"  workload    : {workload_type} ({_rel(workload_path)})")
    print(f"  run-all     : {args.run_all or args.backend == 'simulator'}")
    print(f"  algo        : {args.algo or '(all)'}")
    print(f"  out-dir     : {_rel(out_dir)}")
    print(f"  live-data   : {_rel(live_dir)}")
    print(f"  dry-run     : {dry_run}")
    print("=" * 64)

    if not dry_run:
        ensure_dir(out_dir)
        ensure_dir(live_dir)

    # Before-running phase: analyze -> advise -> guard
    run_workload_analyzer(workload_path, out_dir, dry_run)
    # Feedback CONSUMPTION is opt-in. Snapshot the rule count BEFORE the advise
    # call (rules are generated post-evaluation, so what the advisor consumes is
    # whatever a prior FAIL run left behind). This feeds the manifest honestly.
    feedback_file = out_dir / "feedback_rules.md"
    feedback_rule_count = (
        len(_parse_feedback_rules(feedback_file))
        if args.use_feedback and feedback_file.is_file() else 0
    )
    feedback_consumed = bool(args.use_feedback)
    advisor_fellback = run_advisor(
        out_dir, dry_run, offline_fixture=args.offline_fixture,
        use_feedback=args.use_feedback,
    )
    guard_fellback = run_guard(
        out_dir, dry_run, offline_fixture=args.offline_fixture
    )
    metadata_source = "demo_fallback" if (advisor_fellback or guard_fellback) else None

    # Resolve LLM-selected algorithm + run order (selected first).
    selected = "RR" if dry_run else resolve_selected_algorithm(out_dir)
    run_order = compute_run_order(selected)
    print(f"\n[selected] {selected}; run order: {run_order}")

    # Running phase: execute backend
    if args.backend == "simulator":
        ok = run_simulator_backend(workload_path, out_dir, dry_run)
    else:
        ok = run_xv6_backend(
            out_dir, args.seed, workload_type, run_order, args.algo, dry_run
        )

    if not ok:
        print("\n[FAIL] Backend execution failed. Aborting.")
        return 1

    # After-running phase: ensure metadata + export to live-data + manifest
    print("\n[meta] Checking metadata files")
    ensure_metadata_files(out_dir, dry_run)
    export_to_live_data(
        out_dir, live_dir,
        backend=args.backend, seed=args.seed,
        workload_type=workload_type, workload_stem=workload_stem,
        selected=selected, run_order=run_order, dry_run=dry_run,
        metadata_source=metadata_source,
        feedback_consumed=feedback_consumed,
        feedback_rule_count=feedback_rule_count,
    )

    # Final phase: validate the published live-data against the dashboard
    # contract. Non-strict so a single missing field does not block the demo,
    # but any [WARN]/[ERROR] surfaces in the orchestrator output.
    if not dry_run:
        print("\n[6] Validate dashboard contract")
        rc = subprocess.run(
            [sys.executable, str(TOOLS_DIR / "validate_dashboard_contract.py"),
             "--dir", str(live_dir)],
            capture_output=False,
        ).returncode
        if rc != 0:
            print(f"  [WARN] contract validator exited {rc}")

    # Guarded post-evaluation correction APPLY loop:
    #   event_detector -> correction_proposer -> correction_guard ->
    #   (if FAIL/high-regret) re-run xv6 with the corrected algorithm/params on
    #   the SAME workload -> before/after comparison -> correction_applied.json.
    # This is a host-side closed loop, NOT kernel hot-path LLM control.
    if not dry_run:
        top_metrics = _read_json(out_dir / "metrics.json")
        selected_disp = normalize_algorithm_name(selected)
        rec = _read_json(out_dir / "recommendation.json")
        guard = _read_json(out_dir / "guard_decision.json")
        target_metric = (rec or {}).get("target_metric") or "avg_response_time"
        guard_params = (guard or {}).get("params") or {}
        xv6_profile = workload_type if workload_type in XV6_PROFILES else "mixed"
        mirror_path = XV6_MIRROR_MAP.get(xv6_profile)
        _run_correction_apply_loop(
            out_dir, live_dir,
            backend=args.backend, seed=args.seed, xv6_profile=xv6_profile,
            mirror_path=mirror_path, selected=selected_disp,
            target_metric=target_metric, top_metrics=top_metrics,
            guard_params=guard_params, force_correction=args.force_correction,
            dry_run=dry_run,
        )

    # After-running LLM stages: explain the run, then (FAIL-only) learn from it.
    #   [8] Trace Explainer        -> trace_explanation.json (fresh or explicit
    #                                 unavailable placeholder; never stale)
    #   [9] Feedback Rule Generator-> feedback_rules.md (FAIL judgment only)
    if not dry_run:
        run_trace_explainer(
            out_dir, live_dir, selected,
            offline_fixture=args.offline_fixture, dry_run=dry_run,
        )
        run_feedback_generator(
            out_dir, live_dir,
            offline_fixture=args.offline_fixture, dry_run=dry_run,
        )

    print("\n[DONE] Orchestrator pipeline complete.")
    print("  -> Run: cd dashboard_live && npm run dev")
    return 0


if __name__ == "__main__":
    sys.exit(main())
