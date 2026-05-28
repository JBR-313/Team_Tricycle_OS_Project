#!/usr/bin/env python3
"""export_profile_snapshots.py — publish xv6 profile snapshots for dashboard_live.

For each xv6-supported workload profile, runs the orchestrator, strict-
validates the published live-data, and copies the result into
``dashboard_live/public/live-data/snapshots/<profile>/``. Finally writes
``dashboard_live/public/live-data/snapshots_manifest.json`` listing every
profile snapshot the dashboard can pick from.

The default flat live-data (the one ``scripts/final_demo_check.py``
exercises) is preserved: with ``--restore-default <profile>`` (default
``interactive``) the script restores that profile's snapshot into the flat
root after all per-profile runs complete, so the dashboard's default
view continues to match the on-stage demo path.

See ``docs/profile_snapshot_plan.md`` for the full schema and rationale.

Usage:
    python3 scripts/export_profile_snapshots.py
    python3 scripts/export_profile_snapshots.py --profiles interactive,cpu_bound
    python3 scripts/export_profile_snapshots.py --seed 7 --no-restore-default
    python3 scripts/export_profile_snapshots.py --allow-fallback   # opt in to demo_fallback

Exit codes:
    0  — every requested profile passed orchestrator + strict validator;
         snapshots_manifest.json was written.
    1  — at least one profile failed; partial snapshots may exist.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT / "tools"
SCRIPTS_DIR = ROOT / "scripts"
LIVE_DATA = ROOT / "dashboard_live" / "public" / "live-data"
SNAPSHOTS_DIR = LIVE_DATA / "snapshots"

# Files the dashboard reads. Anything not in this list is left behind in
# the flat root by design (e.g. outputs/_demo_fixtures files won't be copied
# across).
FLAT_FILES = [
    "manifest.json",
    "recommendation.json",
    "guard_decision.json",
    "workload_summary.json",
    "metrics.json",
    "trace_explanation.json",
    "trace_rr.jsonl",
    "trace_fcfs.jsonl",
    "trace_priority.jsonl",
    "trace_mlfq.jsonl",
    "trace_sjf.jsonl",
    "trace_srtf.jsonl",
]

DEFAULT_PROFILES = ["interactive", "cpu_bound", "mixed", "priority_sensitive"]


def _supported_profiles_from_orchestrator() -> set[str]:
    """Lift XV6_PROFILES out of scripts/orchestrator.py without importing it."""
    import re
    text = (SCRIPTS_DIR / "orchestrator.py").read_text(encoding="utf-8")
    m = re.search(r"XV6_PROFILES\s*=\s*\{([^}]*)\}", text)
    if not m:
        return set(DEFAULT_PROFILES)
    return set(re.findall(r'"([^"]+)"', m.group(1))) or set(DEFAULT_PROFILES)


def _run(cmd: list[str]) -> int:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd).returncode


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_orchestrator(profile: str, backend: str, seed: int,
                     allow_fallback: bool = False) -> int:
    cmd = [
        sys.executable, str(SCRIPTS_DIR / "orchestrator.py"),
        "--backend", backend, "--seed", str(seed),
        "--workload", profile, "--run-all",
    ]
    # The orchestrator is strict-by-default about LLM failures. Forward
    # --allow-fallback as --offline-fixture so the snapshot run can still
    # produce demo-fallback artifacts when the caller explicitly asked for
    # them; the metadata_source check below stays the source of truth.
    if allow_fallback:
        cmd.append("--offline-fixture")
    return _run(cmd)


def run_validator_strict(dir_path: Path) -> int:
    return _run([
        sys.executable, str(TOOLS_DIR / "validate_dashboard_contract.py"),
        "--dir", str(dir_path), "--strict",
    ])


def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def copy_flat_into(dst: Path) -> tuple[int, list[str]]:
    """Copy the FLAT_FILES from LIVE_DATA into dst. Returns (count, missing)."""
    dst.mkdir(parents=True, exist_ok=True)
    copied = 0
    missing: list[str] = []
    for f in FLAT_FILES:
        src = LIVE_DATA / f
        if not src.is_file():
            missing.append(f)
            continue
        shutil.copy2(src, dst / f)
        copied += 1
    return copied, missing


def snapshot_one(profile: str, backend: str, seed: int,
                 allow_fallback: bool) -> dict | None:
    """Run + validate + copy one profile. Returns the manifest entry or None on failure."""
    print(f"\n=== snapshot: {profile} ===")
    rc = run_orchestrator(profile, backend, seed, allow_fallback=allow_fallback)
    if rc != 0:
        print(f"[FAIL] orchestrator exited {rc} for {profile}")
        return None
    rc = run_validator_strict(LIVE_DATA)
    if rc != 0:
        print(f"[FAIL] strict validator exited {rc} for {profile}")
        return None

    mf = _read_json(LIVE_DATA / "manifest.json")
    metadata_source = mf.get("metadata_source")
    if metadata_source == "demo_fallback" and not allow_fallback:
        print(f"[FAIL] {profile}: manifest.metadata_source=demo_fallback "
              f"(re-run with --allow-fallback to opt in)")
        return None

    dst = SNAPSHOTS_DIR / profile
    if dst.exists():
        shutil.rmtree(dst)
    copied, missing = copy_flat_into(dst)
    if missing:
        print(f"[WARN] {profile}: missing source files (left out of snapshot): {missing}")
    print(f"  copied {copied} files -> dashboard_live/public/live-data/snapshots/{profile}/")

    metrics = _read_json(LIVE_DATA / "metrics.json")
    entry = {
        "profile": profile,
        "path": f"snapshots/{profile}",
        "backend": mf.get("backend") or backend,
        "seed": mf.get("seed", seed),
        "workload_type": mf.get("workload_type") or profile,
        "llm_selected_algorithm": mf.get("llm_selected_algorithm")
                                  or mf.get("recommended_algorithm"),
        "judgment": metrics.get("judgment"),
        "regret_score": metrics.get("regret_score"),
        "starvation_occurred": metrics.get("starvation_occurred"),
        "generated_at": mf.get("generated_at"),
    }
    if metadata_source:
        entry["metadata_source"] = metadata_source
    return entry


def write_snapshots_manifest(entries: list[dict]) -> None:
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "version": 1,
        "generated_at": _iso_now(),
        "profiles": entries,
    }
    (LIVE_DATA / "snapshots_manifest.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8"
    )
    print(f"\nwrote snapshots_manifest.json ({len(entries)} profile(s))")


def restore_default(profile: str) -> bool:
    """Copy the snapshot for `profile` back into the flat live-data root.

    Idempotent if the snapshot doesn't exist (no-op + warn).
    """
    src = SNAPSHOTS_DIR / profile
    if not src.is_dir():
        print(f"[WARN] cannot restore default — snapshot dir missing: {src}")
        return False
    print(f"\nrestoring default flat live-data ← snapshots/{profile}/")
    for f in FLAT_FILES:
        s = src / f
        if s.is_file():
            shutil.copy2(s, LIVE_DATA / f)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Export per-profile xv6 snapshots for dashboard_live")
    ap.add_argument("--backend", choices=["xv6", "simulator"], default="xv6",
                    help="orchestrator backend (default: xv6 — the final demo path)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--profiles", default=",".join(DEFAULT_PROFILES),
                    help="comma-separated profile names")
    ap.add_argument("--restore-default", default="interactive",
                    help="profile to restore into the flat live-data root after exports "
                         "(default: interactive). Use --no-restore-default to skip.")
    ap.add_argument("--no-restore-default", action="store_true",
                    help="leave flat live-data as whatever the last profile produced")
    ap.add_argument("--allow-fallback", action="store_true",
                    help="commit a snapshot even if metadata_source=demo_fallback "
                         "(no real LLM call). Default refuses such runs.")
    args = ap.parse_args()

    requested = [p.strip() for p in args.profiles.split(",") if p.strip()]
    if args.backend == "xv6":
        supported = _supported_profiles_from_orchestrator()
        skipped = [p for p in requested if p not in supported]
        runnable = [p for p in requested if p in supported]
    else:
        skipped, runnable = [], requested

    print(f"Export profile snapshots (backend={args.backend} seed={args.seed})")
    print(f"  requested : {requested}")
    if skipped:
        print(f"  SKIPPED (no xv6 schedtest table): {skipped}")
    print(f"  runnable  : {runnable}")
    if not runnable:
        print("[FAIL] no runnable profiles")
        return 1

    t0 = time.time()
    entries: list[dict] = []
    failed: list[str] = []
    for profile in runnable:
        e = snapshot_one(profile, args.backend, args.seed, args.allow_fallback)
        if e is None:
            failed.append(profile)
            continue
        entries.append(e)

    if entries:
        write_snapshots_manifest(entries)

    if not args.no_restore_default and entries:
        target = args.restore_default
        if target in [e["profile"] for e in entries]:
            restore_default(target)
        elif entries:
            fallback = entries[0]["profile"]
            print(f"[WARN] requested restore-default profile {target!r} not in successful "
                  f"snapshots; restoring {fallback!r} instead")
            restore_default(fallback)

    elapsed = round(time.time() - t0, 1)
    print()
    print(f"  succeeded: {len(entries)}/{len(runnable)} — {[e['profile'] for e in entries]}")
    if failed:
        print(f"  FAILED   : {len(failed)}/{len(runnable)} — {failed}")
    print(f"  elapsed  : {elapsed}s")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
