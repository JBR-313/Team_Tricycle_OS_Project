#!/usr/bin/env python3
"""
orchestrator.py — host-side control plane for LLM Sched Copilot (Phase B).

Runs the full host-side pipeline end-to-end:

    workload selection
        -> workload_analyzer   (workload_summary.json)
        -> llm_advisor         (recommendation.json; demo fallback if no API key)
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
DEMO_DIR = ROOT / "outputs" / "demo"
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
)
from metrics import compute as compute_metrics  # noqa: E402

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
    "interactive":        ROOT / "workloads" / "interactive_heavy.json",
    "cpu_bound":          ROOT / "workloads" / "long_cpu_bound_first.json",
    "mixed":              ROOT / "workloads" / "mixed_workload.json",
    "priority_sensitive": ROOT / "workloads" / "priority_sensitive.json",
    "short_jobs":         ROOT / "workloads" / "short_jobs.json",
    "starvation_risk":    ROOT / "workloads" / "starvation_risk.json",
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


def run_advisor(out_dir: Path, dry_run: bool):
    """Run llm_advisor (advise). On ANY failure, fall back to demo recommendation."""
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
        return

    ok = False
    try:
        rc = subprocess.run(cmd, capture_output=False).returncode
        ok = rc == 0 and rec_out.exists()
        if not ok:
            print(f"  [advisor] exited {rc}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [advisor] exception: {exc}")
        ok = False

    if not ok:
        print("[advisor] no API key / failed -> using demo recommendation fallback")
        demo_rec = DEMO_DIR / "recommendation.json"
        if not demo_rec.exists():
            sys.exit(f"[orchestrator] demo recommendation fallback missing: {demo_rec}")
        copy_file(demo_rec, rec_out, dry_run)


def run_guard(out_dir: Path, dry_run: bool):
    """Run algorithm_guard. On failure, fall back to demo guard_decision."""
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
        return

    ok = False
    try:
        rc = subprocess.run(cmd, capture_output=False).returncode
        ok = rc == 0 and guard_out.exists()
        if not ok:
            print(f"  [guard] exited {rc}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [guard] exception: {exc}")
        ok = False

    if not ok:
        print("[guard] failed -> using demo guard_decision fallback")
        demo_guard = DEMO_DIR / "guard_decision.json"
        if not demo_guard.exists():
            sys.exit(f"[orchestrator] demo guard fallback missing: {demo_guard}")
        copy_file(demo_guard, guard_out, dry_run)

    # Schema-drift bridge: algorithm_guard.py writes the key `algorithm`, but the
    # simulator reads `scheduling_algorithm` (falling back to MLFQ otherwise,
    # which mis-applies params). Mirror the resolved algo onto both keys so the
    # downstream simulator always sees the LLM-selected algorithm. We only touch
    # the guard_decision.json in out_dir (tools/* are left untouched).
    if not dry_run:
        guard = _read_json(guard_out)
        if guard:
            algo = get_guard_algorithm(guard, default="RR")
            if guard.get("scheduling_algorithm") != algo:
                guard["scheduling_algorithm"] = algo
                guard_out.write_text(json.dumps(guard, indent=2) + "\n")
                print(f"  [guard] mirrored scheduling_algorithm={algo} for simulator compat")


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
                       dry_run: bool) -> bool:
    """Boot xv6 under QEMU, run one schedtest, capture the console to raw_path.

    Waits for the shell, types `schedtest <algo> <seed> <profile>`, then waits for
    the RUN_END marker (or a timeout) and quits QEMU via Ctrl-A x.  Returns True
    if a RUN_END for this run was captured.
    """
    cmd = f"schedtest {algo_lower} {seed} {profile}"
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


def _extract_run_window(raw_path: Path) -> str:
    """Return only the lines between RUN_BEGIN and RUN_END (inclusive)."""
    out: list[str] = []
    in_win = False
    for ln in raw_path.read_text().splitlines():
        if "event=RUN_BEGIN" in ln:
            in_win = True
        if in_win:
            out.append(ln)
        if "event=RUN_END" in ln:
            break
    return "\n".join(out) + "\n"


def parse_xv6_log(raw_path: Path, algo: str, seed: int, profile: str,
                  out_dir: Path, dry_run: bool) -> bool:
    """Window the raw log to the run, parse to trace_<algo>.jsonl, then force the
    algo label and rebase ticks so the run starts at t=0 (children fork together,
    so a 0-based clock yields correct relative response/turnaround/waiting)."""
    trace_out = out_dir / f"trace_{algo.lower()}.jsonl"
    if dry_run:
        print(f"  [DRY-RUN] parse {_rel(raw_path)} -> {_rel(trace_out)}")
        return True

    window = _extract_run_window(raw_path)
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
        full[algo] = m
        comparison[algo] = {
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
    vals = [c[mkey] for c in comparison.values()]
    best = min(vals) if lower_better else max(vals)

    def _judge(v: float) -> tuple[str, float]:
        delta = abs(v - best) / (abs(best) + 1e-9)
        j = "SUCCESS" if delta < 0.05 else ("NEAR-SUCCESS" if delta < 0.25 else "FAIL")
        return j, round(delta, 3)

    for c in comparison.values():
        c["judgment"], _ = _judge(c[mkey])

    if selected not in full:
        selected = next(iter(full))
    top = dict(full[selected])
    top["scheduling_algorithm"] = selected
    top["params"] = guard_params or {}
    top["comparison"] = comparison
    top["judgment"], top["regret_score"] = _judge(comparison[selected][mkey])
    top.setdefault("starvation_pids", [])

    (out_dir / "metrics.json").write_text(json.dumps(top, indent=2))
    print(f"  metrics.json: selected={selected} judgment={top['judgment']} "
          f"regret={top['regret_score']}")
    return True


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

    parsed_any = False
    for a in algos:
        raw_path = RAW_LOG_DIR / f"xv6_raw_{a.lower()}_seed{seed}.log"
        if not qemu_run_schedtest(a.lower(), seed, xv6_profile, raw_path, dry_run):
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
    """Safety net: copy any missing metadata file from outputs/demo."""
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


def export_to_live_data(out_dir: Path, live_dir: Path, *, backend: str, seed: int,
                        workload_type: str, workload_stem: str, selected: str,
                        run_order: list[str], dry_run: bool) -> dict:
    print(f"\n[5] Export to {_rel(live_dir)}")
    ensure_dir(live_dir)

    for algo in TRACE_ALGOS:
        copy_file(out_dir / f"trace_{algo}.jsonl", live_dir / f"trace_{algo}.jsonl", dry_run)

    copy_file(out_dir / "metrics.json", live_dir / "metrics.json", dry_run)
    for fname in META_FILES:
        copy_file(out_dir / fname, live_dir / fname, dry_run)

    # target_metric from recommendation, else default
    rec = _read_json(out_dir / "recommendation.json")
    target = rec.get("target_metric") or "avg_response_time"

    # version increment from existing manifest
    existing = _read_json(live_dir / "manifest.json")
    version = int(existing.get("version", 0)) + 1

    now = _iso_now()
    mode = "simulator" if backend == "simulator" else "xv6-log"

    manifest = {
        # ── new (additive) fields ──
        "backend": backend,
        "seed": seed,
        "workload_type": workload_type,
        "llm_selected_algorithm": selected,
        "algorithms_executed": run_order,
        "generated_at": now,
        "orchestrator_version": ORCHESTRATOR_VERSION,
        # ── legacy mirrors (keep the current dashboard working) ──
        "mode": mode,
        "updated_at": now,
        "version": version,
        "workload": workload_stem,
        "algorithms": run_order,
        "recommended_algorithm": selected,
        "target_metric": target,
    }
    write_json(live_dir / "manifest.json", manifest, dry_run)
    print(f"  manifest version -> {version}")
    return manifest


# ── main ────────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(
        description="LLM Sched Copilot — host-side Orchestrator (Phase B)"
    )
    p.add_argument("--backend", choices=["xv6", "simulator"], default="simulator")
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
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    live_dir = Path(args.live_data_dir)
    dry_run = args.dry_run

    workload_type, workload_path = resolve_workload(args.workload)
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
    run_advisor(out_dir, dry_run)
    run_guard(out_dir, dry_run)

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
    )

    print("\n[DONE] Orchestrator pipeline complete.")
    print("  -> Run: cd dashboard_live && npm run dev")
    return 0


if __name__ == "__main__":
    sys.exit(main())
