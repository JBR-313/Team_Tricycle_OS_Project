#!/usr/bin/env python3
"""
run_live_dashboard_pipeline.py

Generate dashboard_live/public/live-data/* from host-side simulator outputs.

Usage:
    python3 scripts/run_live_dashboard_pipeline.py [options]

Options:
    --workload PATH        Workload JSON file (default: workloads/interactive_heavy.json)
    --mode simulator       Data source mode: simulator (default) or xv6-log
    --xv6-log PATH         Path to raw xv6 console log (for --mode xv6-log)
    --out-dir PATH         Simulator output directory (default: outputs/live)
    --live-data-dir PATH   Dashboard live-data output dir (default: dashboard_live/public/live-data)
    --dry-run              Show what would be done without writing files
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
TOOLS_DIR  = ROOT / "tools"
OUTPUTS    = ROOT / "outputs" / "live"
LIVE_DATA  = ROOT / "dashboard_live" / "public" / "live-data"
WORKLOAD   = ROOT / "workloads" / "interactive_heavy.json"


# ── helpers ───────────────────────────────────────────────────────────────────

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, dst: Path, dry_run: bool = False):
    if not src.exists():
        print(f"  [WARN] missing: {src}")
        return
    print(f"  copy  {src.relative_to(ROOT)} → {dst.relative_to(ROOT)}")
    if not dry_run:
        shutil.copy2(src, dst)


def write_json(path: Path, data: dict, dry_run: bool = False):
    print(f"  write {path.relative_to(ROOT)}")
    if not dry_run:
        path.write_text(json.dumps(data, indent=2))


# ── simulator run ─────────────────────────────────────────────────────────────

def run_simulator(workload: Path, out_dir: Path, dry_run: bool):
    guard_file = out_dir / "guard_decision.json"
    if not guard_file.exists():
        guard_file = ROOT / "outputs" / "demo" / "guard_decision.json"

    cmd = [
        sys.executable, str(TOOLS_DIR / "scheduler_simulator.py"),
        "--workload", str(workload),
        "--guard", str(guard_file),
        "--out-dir", str(out_dir),
    ]
    print(f"\n[1] Running simulator: {' '.join(cmd)}")
    if dry_run:
        print("  [DRY-RUN] skipped")
        return True

    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"  [ERROR] Simulator exited with code {result.returncode}")
        return False
    return True


# ── xv6-log mode ──────────────────────────────────────────────────────────────

def run_xv6_log(xv6_log: Path, out_dir: Path, dry_run: bool):
    """Parse raw xv6 console log into JSONL traces + metrics."""
    print(f"\n[1] Parsing xv6 log: {xv6_log}")
    if not xv6_log.exists():
        print(f"  [ERROR] xv6 log not found: {xv6_log}")
        return False

    # Use trace_parser.py
    parser_cmd = [
        sys.executable, str(TOOLS_DIR / "trace_parser.py"),
        "--input", str(xv6_log),
        "--out-dir", str(out_dir),
    ]
    print(f"  cmd: {' '.join(parser_cmd)}")
    if dry_run:
        print("  [DRY-RUN] skipped")
        return True

    result = subprocess.run(parser_cmd, capture_output=False)
    if result.returncode != 0:
        print(f"  [WARN] trace_parser exited {result.returncode} — continuing")

    # Use metrics.py on parsed traces
    metrics_cmd = [
        sys.executable, str(TOOLS_DIR / "metrics.py"),
        "--traces-dir", str(out_dir),
        "--output", str(out_dir / "metrics.json"),
    ]
    print(f"  cmd: {' '.join(metrics_cmd)}")
    result = subprocess.run(metrics_cmd, capture_output=False)
    if result.returncode != 0:
        print(f"  [WARN] metrics.py exited {result.returncode} — continuing")

    return True


# ── metadata generation ────────────────────────────────────────────────────────

def ensure_metadata_files(out_dir: Path, workload_path: Path, dry_run: bool):
    """
    If recommendation.json / guard_decision.json / workload_summary.json
    are missing from out_dir, copy them from outputs/demo as a safe fallback.
    """
    demo_dir = ROOT / "outputs" / "demo"
    for fname in ("recommendation.json", "guard_decision.json",
                  "workload_summary.json", "trace_explanation.json"):
        target = out_dir / fname
        if not target.exists():
            src = demo_dir / fname
            if src.exists():
                print(f"  [meta] using demo fallback for {fname}")
                if not dry_run:
                    shutil.copy2(src, target)
            else:
                print(f"  [WARN] no source for {fname}")


# ── copy to live-data ──────────────────────────────────────────────────────────

TRACE_ALGOS = ["rr", "fcfs", "priority", "mlfq", "sjf", "srtf"]

def copy_to_live_data(out_dir: Path, live_dir: Path, workload_path: Path,
                      mode: str, dry_run: bool):
    print(f"\n[3] Copying to {live_dir.relative_to(ROOT)}")
    ensure_dir(live_dir)

    for algo in TRACE_ALGOS:
        copy_file(out_dir / f"trace_{algo}.jsonl", live_dir / f"trace_{algo}.jsonl", dry_run)

    for fname in ("metrics.json", "recommendation.json", "guard_decision.json",
                  "workload_summary.json", "trace_explanation.json"):
        copy_file(out_dir / fname, live_dir / fname, dry_run)

    # Build manifest
    try:
        metrics_raw = json.loads((out_dir / "metrics.json").read_text())
        rec_raw     = json.loads((out_dir / "recommendation.json").read_text())
        algos       = list(metrics_raw.get("comparison", {}).keys()) or \
                      [a.upper() for a in TRACE_ALGOS]
        rec_algo    = rec_raw.get("recommended_scheduling_algorithm", "RR")
        target      = rec_raw.get("target_metric", "avg_response_time")
        workload_name = workload_path.stem
    except Exception:
        algos, rec_algo, target = ["RR", "FCFS", "Priority", "MLFQ", "SJF", "SRTF"], "RR", "avg_response_time"
        workload_name = workload_path.stem

    existing = {}
    manifest_path = live_dir / "manifest.json"
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text())
        except Exception:
            pass

    manifest = {
        "mode":                  mode,
        "updated_at":            datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "version":               existing.get("version", 0) + 1,
        "workload":              workload_name,
        "algorithms":            algos,
        "recommended_algorithm": rec_algo,
        "target_metric":         target,
    }
    write_json(live_dir / "manifest.json", manifest, dry_run)
    print(f"  manifest version → {manifest['version']}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="LLM Sched Copilot — Live Dashboard Pipeline")
    p.add_argument("--workload",      default=str(WORKLOAD))
    p.add_argument("--mode",          choices=["simulator", "xv6-log"], default="simulator")
    p.add_argument("--xv6-log",       default=None)
    p.add_argument("--out-dir",       default=str(OUTPUTS))
    p.add_argument("--live-data-dir", default=str(LIVE_DATA))
    p.add_argument("--dry-run",       action="store_true")
    args = p.parse_args()

    workload_path  = Path(args.workload)
    out_dir        = Path(args.out_dir)
    live_dir       = Path(args.live_data_dir)
    dry_run        = args.dry_run

    print("=" * 60)
    print("LLM Sched Copilot — Live Dashboard Pipeline")
    print(f"  mode      : {args.mode}")
    print(f"  workload  : {workload_path}")
    print(f"  out-dir   : {out_dir}")
    print(f"  live-data : {live_dir}")
    print(f"  dry-run   : {dry_run}")
    print("=" * 60)

    if not dry_run:
        ensure_dir(out_dir)
        ensure_dir(live_dir)

    # Step 1 — generate traces
    if args.mode == "simulator":
        ok = run_simulator(workload_path, out_dir, dry_run)
    else:  # xv6-log
        if not args.xv6_log:
            print("[ERROR] --xv6-log PATH required for xv6-log mode")
            sys.exit(1)
        ok = run_xv6_log(Path(args.xv6_log), out_dir, dry_run)

    if not ok:
        print("\n[FAIL] Data generation step failed. Aborting.")
        sys.exit(1)

    # Step 2 — ensure metadata
    print("\n[2] Checking metadata files")
    ensure_metadata_files(out_dir, workload_path, dry_run)

    # Step 3 — copy to live-data
    copy_to_live_data(out_dir, live_dir, workload_path, args.mode, dry_run)

    print("\n[DONE] Live-data pipeline complete.")
    print(f"  → Run: cd dashboard_live && npm run dev")


if __name__ == "__main__":
    main()
