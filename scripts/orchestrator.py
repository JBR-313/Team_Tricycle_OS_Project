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
from metrics import compute_metrics  # noqa: E402

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
XV6_PROFILES = {"interactive", "cpu_bound", "mixed", "priority_sensitive"}
QEMU_BOOT_WAIT = 4.0      # seconds to wait for the shell prompt before typing
QEMU_RUN_TIMEOUT = 60.0   # max seconds to wait for RUN_END before giving up

# Profile name -> workload file (the user chose: map to existing JSON, do NOT synthesize).
PROFILE_MAP = {
    # Legacy xv6 profile aliases (kept for backward compat with schedtest).
    "interactive":        ROOT / "workloads" / "interactive_heavy.json",
    "cpu_bound":          ROOT / "workloads" / "long_cpu_bound_first.json",
    "mixed":              ROOT / "workloads" / "mixed_workload.json",
    "priority_sensitive": ROOT / "workloads" / "priority_sensitive.json",
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


def run_advisor(out_dir: Path, dry_run: bool, *, offline_fixture: bool = False) -> bool:
    """Run llm_advisor (advise).

    Default behavior is STRICT: if the advisor fails (missing UPSTAGE_API_KEY,
    network error, schema error, etc.) the orchestrator exits with a clear
    error so we never silently fake a real Solar Pro 3 call. To use the
    committed demo recommendation as a fixture, pass --offline-fixture.

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
                  out_dir: Path, dry_run: bool) -> bool:
    """Window the raw log to the run, parse to trace_<algo>.jsonl, then force the
    algo label and rebase ticks so the run starts at t=0 (children fork together,
    so a 0-based clock yields correct relative response/turnaround/waiting)."""
    trace_out = out_dir / f"trace_{algo.lower()}.jsonl"
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
                      dry_run: bool) -> bool:
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
    top["params"] = guard_params or {}
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
    """Build schedtest predictor CLI tokens for SJF/SRTF from the guard decision.

    Layout (consumed by user/schedtest.c):
        alpha initial min max  h0 h1 ...
    where alpha..max come from guard_decision.params (the Guard-validated
    predictor parameters) and hN are per-process initial burst priors aligned to
    the mirror workload's process order == schedtest fork order. Returns None if
    no usable params/priors are available (schedtest then uses kernel defaults).

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

    tokens = [str(alpha), str(initial), str(min_b), str(max_b)]

    # Per-process priors aligned to fork order via the mirror workload.
    mirror = _read_json(mirror_path) if mirror_path else None
    procs = (mirror or {}).get("processes") or []
    for p in procs:
        entry = by_pid.get(p.get("pid"))
        pb = entry.get("predicted_burst") if isinstance(entry, dict) else None
        if not isinstance(pb, int) or pb < 1:
            pb = initial  # no LLM prior for this process -> predictor initial
        tokens.append(str(pb))
    return tokens


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

    parsed_any = False
    for a in algos:
        raw_path = RAW_LOG_DIR / f"xv6_raw_{a.lower()}_seed{seed}.log"
        a_pred = pred_args if a.upper() in ("SJF", "SRTF") else None
        if not qemu_run_schedtest(a.lower(), seed, xv6_profile, raw_path, dry_run, a_pred):
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
                             target_metric, dry_run)


# ── metadata + export (after running) ──────────────────────────────────────────

def ensure_metadata_files(out_dir: Path, dry_run: bool):
    """Safety net: copy any missing metadata file from outputs/_demo_fixtures."""
    for fname in META_FILES:
        target = out_dir / fname
        if not target.exists():
            src = DEMO_DIR / fname
            if src.exists():
                print(f"  [meta] using demo fallback for {fname}")
                if not dry_run:
                    shutil.copy2(src, target)
            else:
                print(f"  [WARN] no source for {fname}")


def _run_correction_preview(out_dir: Path, live_dir: Path, selected_algo: str) -> None:
    """Run event_detector -> correction_proposer -> correction_guard.

    All preview-only — files carry preview_only=true / applied=false and
    are NOT applied to xv6. The pipeline is non-blocking: any failure
    surfaces as a [WARN] and the demo continues.
    """
    print("\n[7] Runtime correction preview (preview-only, no xv6 apply)")
    rec = live_dir / "recommendation.json"
    metrics = live_dir / "metrics.json"
    trace = live_dir / f"trace_{selected_algo.lower()}.jsonl"
    if not (rec.is_file() and metrics.is_file() and trace.is_file()):
        print("  [skip] missing recommendation/metrics/trace; preview not run")
        return

    events_out = out_dir / "runtime_events.json"
    proposal_out = out_dir / "correction_proposal.json"
    decision_out = out_dir / "correction_guard_decision.json"
    # Drop any prior preview artifacts so a clean run with no events leaves
    # nothing stale behind for the dashboard to read.
    for p in (events_out, proposal_out, decision_out,
              live_dir / "runtime_events.json",
              live_dir / "correction_proposal.json",
              live_dir / "correction_guard_decision.json"):
        try:
            p.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass

    rc = subprocess.run(
        [sys.executable, str(TOOLS_DIR / "event_detector.py"),
         "--trace", str(trace), "--metrics", str(metrics),
         "--out", str(events_out)],
        capture_output=False,
    ).returncode
    if rc != 0 or not events_out.is_file():
        print(f"  [WARN] event_detector exited {rc}; preview skipped")
        return

    # event_detector always writes a file; check whether it contains events.
    events_doc = _read_json(events_out)
    if not (isinstance(events_doc, dict) and events_doc.get("events")):
        print("  [info] no runtime events detected — preview omitted (dashboard hides card)")
        copy_file(events_out, live_dir / "runtime_events.json", False)
        return

    copy_file(events_out, live_dir / "runtime_events.json", False)

    rc = subprocess.run(
        [sys.executable, str(TOOLS_DIR / "correction_proposer.py"),
         "--events", str(events_out), "--recommendation", str(rec),
         "--out", str(proposal_out)],
        capture_output=False,
    ).returncode
    if rc != 0 or not proposal_out.is_file():
        print(f"  [WARN] correction_proposer exited {rc}; preview stops at events")
        return
    copy_file(proposal_out, live_dir / "correction_proposal.json", False)

    rc = subprocess.run(
        [sys.executable, str(TOOLS_DIR / "correction_guard.py"),
         "--proposal", str(proposal_out), "--out", str(decision_out)],
        capture_output=False,
    ).returncode
    if rc != 0 or not decision_out.is_file():
        print(f"  [WARN] correction_guard exited {rc}; preview stops at proposal")
        return
    copy_file(decision_out, live_dir / "correction_guard_decision.json", False)
    print("  preview published (preview_only=true, applied=false)")


def export_to_live_data(out_dir: Path, live_dir: Path, *, backend: str, seed: int,
                        workload_type: str, workload_stem: str, selected: str,
                        run_order: list[str], dry_run: bool,
                        metadata_source: str | None = None) -> dict:
    print(f"\n[5] Export to {_rel(live_dir)}")
    ensure_dir(live_dir)

    for algo in TRACE_ALGOS:
        copy_file(out_dir / f"trace_{algo}.jsonl", live_dir / f"trace_{algo}.jsonl", dry_run)

    copy_file(out_dir / "metrics.json", live_dir / "metrics.json", dry_run)
    for fname in META_FILES:
        copy_file(out_dir / fname, live_dir / fname, dry_run)

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

    workload_stem = workload_path.stem

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
    advisor_fellback = run_advisor(
        out_dir, dry_run, offline_fixture=args.offline_fixture
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

    # Optional preview-only runtime-correction loop:
    #   event_detector -> correction_proposer -> correction_guard
    # Files land alongside the flat live-data and are picked up by the
    # dashboard's RuntimeCorrectionPreview card (added in a follow-up PR).
    # Nothing is applied to xv6 — preview_only=true, applied=false.
    if not dry_run:
        _run_correction_preview(out_dir, live_dir, selected)

    print("\n[DONE] Orchestrator pipeline complete.")
    print("  -> Run: cd dashboard_live && npm run dev")
    return 0


if __name__ == "__main__":
    sys.exit(main())
