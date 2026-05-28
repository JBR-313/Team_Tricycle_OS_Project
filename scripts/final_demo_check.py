#!/usr/bin/env python3
"""final_demo_check.py — one-command presenter sanity script.

Runs the host-side checks needed before walking on stage and shows the
single next command to start the dashboard. Does NOT auto-open a browser.

Stages (each one fails the script if it errors out):
  1. Compile every Python file under tools/ and scripts/.
  2. Run the Orchestrator on the xv6 backend with seed 42 / interactive.
  3. Strict-validate the published dashboard live-data.

On success the script prints the dashboard launch command but does not
spawn `npm` — the presenter starts the dev server themselves so they
control which terminal owns it.

Usage:
    python3 scripts/final_demo_check.py
    python3 scripts/final_demo_check.py --seed 7 --workload mixed
    python3 scripts/final_demo_check.py --backend simulator   # fallback path
    python3 scripts/final_demo_check.py --skip-orchestrator   # only compile + validate

Exit status:
    0  — every stage passed; safe to demo.
    1+ — first stage that failed (other stages are skipped).
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT / "tools"
SCRIPTS_DIR = ROOT / "scripts"
LIVE_DATA = ROOT / "dashboard_live" / "public" / "live-data"


def _section(n: int, total: int, title: str) -> None:
    print()
    print(f"=== [{n}/{total}] {title} ===")


def _run(cmd: list[str], cwd: Path | None = None) -> int:
    print(f"$ {' '.join(shlex.quote(c) for c in cmd)}")
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None).returncode


def stage_py_compile() -> int:
    """Compile every .py under tools/ and scripts/. Skips __pycache__."""
    files: list[str] = []
    for d in (TOOLS_DIR, SCRIPTS_DIR):
        for p in sorted(d.glob("*.py")):
            files.append(str(p))
    if not files:
        print("[WARN] no Python files found to compile")
        return 0
    return _run([sys.executable, "-m", "py_compile", *files])


def stage_orchestrator(backend: str, seed: int, workload: str,
                       offline_fixture: bool = False) -> int:
    cmd = [
        sys.executable, str(SCRIPTS_DIR / "orchestrator.py"),
        "--backend", backend,
        "--seed", str(seed),
        "--workload", workload,
        "--run-all",
    ]
    if offline_fixture:
        cmd.append("--offline-fixture")
    return _run(cmd)


def stage_validate(strict: bool) -> int:
    cmd = [
        sys.executable, str(TOOLS_DIR / "validate_dashboard_contract.py"),
        "--dir", str(LIVE_DATA),
    ]
    if strict:
        cmd.append("--strict")
    return _run(cmd)


def main() -> int:
    ap = argparse.ArgumentParser(description="Pre-demo sanity check (no browser launch)")
    ap.add_argument("--backend", choices=["xv6", "simulator"], default="xv6",
                    help="orchestrator backend (default: xv6 — the final demo path)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--workload", default="interactive")
    ap.add_argument("--skip-orchestrator", action="store_true",
                    help="only compile + validate the existing live-data")
    ap.add_argument("--no-strict-validator", action="store_true",
                    help="run the contract validator without --strict")
    ap.add_argument("--offline-fixture", action="store_true",
                    help=("forward --offline-fixture to the orchestrator so the "
                          "committed outputs/_demo_fixtures/ fixtures are used when "
                          "UPSTAGE_API_KEY is missing. Default is STRICT."))
    args = ap.parse_args()

    stages: list[tuple[str, callable]] = []  # type: ignore[type-arg]
    stages.append(("Compile tools/ and scripts/ Python", stage_py_compile))
    if not args.skip_orchestrator:
        stages.append((
            f"Run Orchestrator (backend={args.backend} seed={args.seed} "
            f"workload={args.workload})",
            lambda: stage_orchestrator(args.backend, args.seed, args.workload,
                                       offline_fixture=args.offline_fixture),
        ))
    stages.append((
        "Strict-validate dashboard contract"
        if not args.no_strict_validator else
        "Validate dashboard contract (non-strict)",
        lambda: stage_validate(not args.no_strict_validator),
    ))

    total = len(stages)
    for i, (title, fn) in enumerate(stages, start=1):
        _section(i, total, title)
        rc = fn()
        if rc != 0:
            print()
            print(f"[FAIL] stage {i}/{total} ({title}) exited {rc}")
            print("       Fix the failure above before demoing.")
            return rc

    print()
    print("=" * 64)
    print("[OK] All pre-demo checks passed.")
    print()
    if args.backend == "xv6":
        print("  Dashboard data is from the xv6 backend (final demo path).")
    else:
        print("  Dashboard data is from the simulator (dev / fallback path).")
        print("  The dashboard header will show 'SIMULATOR FALLBACK'.")
    print()
    print("Next step (run in another terminal — the script will NOT auto-open):")
    print("  cd dashboard_live && npm run dev")
    print()
    print("Then open http://localhost:5174 and walk the demo per docs/demo_runbook.md")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
