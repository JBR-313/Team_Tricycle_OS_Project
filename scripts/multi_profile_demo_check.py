#!/usr/bin/env python3
"""multi_profile_demo_check.py — broader confidence than the single demo run.

Runs the xv6 orchestrator + strict contract validator across every curated
schedtest profile in turn (interactive, cpu_bound, mixed, priority_sensitive)
and prints one compact pass/fail summary at the end. Each profile re-uses
the same `dashboard_live/public/live-data/` directory the orchestrator
already writes to — the published live-data after this script reflects the
LAST profile run, by design.

This is intentionally NOT a substitute for `scripts/final_demo_check.py`:
the on-stage demo path remains `--backend xv6 --seed 42 --workload
interactive --run-all`. This script is for broader pre-demo confidence.

Usage:
    python3 scripts/multi_profile_demo_check.py
    python3 scripts/multi_profile_demo_check.py --seed 7
    python3 scripts/multi_profile_demo_check.py --profiles interactive,mixed
    python3 scripts/multi_profile_demo_check.py --backend simulator   # fast

Exit status:
    0  — every requested profile passed orchestrator + strict validator.
    1  — at least one profile failed; details in the summary table.

Constraint: this script never commits the generated live-data. The
caller should ``git stash`` or discard ``dashboard_live/public/live-data/``
churn before opening a PR.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT / "tools"
SCRIPTS_DIR = ROOT / "scripts"
LIVE_DATA = ROOT / "dashboard_live" / "public" / "live-data"

# Curated schedtest profiles — must mirror scripts/orchestrator.py:XV6_PROFILES.
# If the orchestrator grows new curated profiles, add them here too.
DEFAULT_PROFILES = ["interactive", "cpu_bound", "mixed", "priority_sensitive"]


def _run(cmd: list[str]) -> int:
    print(f"$ {' '.join(shlex.quote(c) for c in cmd)}")
    return subprocess.run(cmd).returncode


def _supported_profiles_from_orchestrator() -> set[str]:
    """Read XV6_PROFILES from the orchestrator without importing the module.

    Importing scripts/orchestrator.py would also run its top-level imports;
    a simple regex lift keeps this script side-effect-free.
    """
    text = (SCRIPTS_DIR / "orchestrator.py").read_text(encoding="utf-8")
    # Look for the set literal assignment. Default to the goal list so the
    # script still works if the source format changes.
    import re
    m = re.search(r"XV6_PROFILES\s*=\s*\{([^}]*)\}", text)
    if not m:
        return set(DEFAULT_PROFILES)
    items = re.findall(r'"([^"]+)"', m.group(1))
    return set(items) if items else set(DEFAULT_PROFILES)


def run_one(profile: str, backend: str, seed: int) -> dict:
    """Run orchestrator + strict validator for one profile. Capture summary."""
    t0 = time.time()
    rec: dict = {
        "profile": profile, "backend": backend, "seed": seed,
        "orchestrator_rc": None, "validator_rc": None,
        "manifest_backend": None, "manifest_version": None,
        "llm_selected": None, "judgment": None,
        "regret_score": None, "starvation_occurred": None,
        "elapsed_s": None,
    }

    print(f"\n--- profile: {profile} ---")
    rc = _run([
        sys.executable, str(SCRIPTS_DIR / "orchestrator.py"),
        "--backend", backend,
        "--seed", str(seed),
        "--workload", profile,
        "--run-all",
    ])
    rec["orchestrator_rc"] = rc
    if rc != 0:
        rec["elapsed_s"] = round(time.time() - t0, 1)
        return rec

    rc = _run([
        sys.executable, str(TOOLS_DIR / "validate_dashboard_contract.py"),
        "--dir", str(LIVE_DATA),
        "--strict",
    ])
    rec["validator_rc"] = rc

    # Pull post-run snapshot from the published live-data.
    try:
        m = json.loads((LIVE_DATA / "manifest.json").read_text(encoding="utf-8"))
        mt = json.loads((LIVE_DATA / "metrics.json").read_text(encoding="utf-8"))
        rec["manifest_backend"] = m.get("backend") or m.get("mode")
        rec["manifest_version"] = m.get("version")
        rec["llm_selected"] = (
            m.get("llm_selected_algorithm") or m.get("recommended_algorithm")
        )
        rec["judgment"] = mt.get("judgment")
        rec["regret_score"] = mt.get("regret_score")
        rec["starvation_occurred"] = mt.get("starvation_occurred")
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARN] failed to read live-data snapshot: {exc}")

    rec["elapsed_s"] = round(time.time() - t0, 1)
    return rec


def _is_pass(rec: dict) -> bool:
    return rec.get("orchestrator_rc") == 0 and rec.get("validator_rc") == 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run xv6 orchestrator + strict validator across schedtest profiles"
    )
    ap.add_argument("--backend", choices=["xv6", "simulator"], default="xv6",
                    help="orchestrator backend (default: xv6 — the final demo path)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--profiles", default=",".join(DEFAULT_PROFILES),
                    help="comma-separated profile names")
    args = ap.parse_args()

    requested = [p.strip() for p in args.profiles.split(",") if p.strip()]

    # For xv6: refuse to silently substitute unsupported profiles. Report and
    # skip them — the goal explicitly says "do not fake support".
    if args.backend == "xv6":
        supported = _supported_profiles_from_orchestrator()
        skipped = [p for p in requested if p not in supported]
        runnable = [p for p in requested if p in supported]
    else:
        skipped = []
        runnable = requested

    print(f"Multi-profile demo check (backend={args.backend} seed={args.seed})")
    print(f"  requested : {requested}")
    if skipped:
        print(f"  SKIPPED (xv6 has no curated schedtest table for these): {skipped}")
    print(f"  runnable  : {runnable}")
    if not runnable:
        print("[FAIL] no runnable profiles")
        return 1

    results = [run_one(p, args.backend, args.seed) for p in runnable]

    # Summary
    print()
    print("=" * 78)
    print("multi-profile summary")
    print("=" * 78)
    header = (
        f"{'profile':<22} {'orch':>5} {'val':>5} {'judgement':<14} "
        f"{'regret':>7} {'starv':>5} {'sel':<8} {'ver':>4} {'sec':>5}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r['profile']:<22} "
            f"{(r['orchestrator_rc'] if r['orchestrator_rc'] is not None else '-'):>5} "
            f"{(r['validator_rc'] if r['validator_rc'] is not None else '-'):>5} "
            f"{str(r['judgment'] or '-'):<14} "
            f"{str(r['regret_score']) if r['regret_score'] is not None else '-':>7} "
            f"{str(r['starvation_occurred']) if r['starvation_occurred'] is not None else '-':>5} "
            f"{str(r['llm_selected'] or '-'):<8} "
            f"{str(r['manifest_version']) if r['manifest_version'] is not None else '-':>4} "
            f"{str(r['elapsed_s']) if r['elapsed_s'] is not None else '-':>5}"
        )
    if skipped:
        print()
        print(f"skipped (no xv6 schedtest table): {skipped}")

    passed = [r for r in results if _is_pass(r)]
    failed = [r for r in results if not _is_pass(r)]
    print()
    print(f"  passed : {len(passed)}/{len(results)} — {[r['profile'] for r in passed]}")
    if failed:
        print(f"  FAILED : {len(failed)}/{len(results)} — {[r['profile'] for r in failed]}")

    # Reminder: do not commit the live-data churn this script produced.
    print()
    print("note: this script overwrites dashboard_live/public/live-data/ on each profile.")
    print("      do NOT commit that churn — `git stash push dashboard_live/public/live-data`")
    print("      or `git checkout -- dashboard_live/public/live-data` after inspecting.")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
