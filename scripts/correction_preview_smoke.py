#!/usr/bin/env python3
"""correction_preview_smoke.py — exercise the proposer + guard from synthetic events.

The healthy on-stage demo (`final_demo_check.py` on xv6 interactive
seed=42) does not trip the runtime event detector — see
`docs/runtime_correction_preview_demo_gap.md`. This script lets a
presenter (or CI) show that the proposer + guard path actually works:
for each canonical event type, it builds an in-memory
`runtime_events` payload, runs `tools/correction_proposer.py` and
`tools/correction_guard.py` against it in a temp directory, and
prints a compact pass/fail summary.

Read-only — never touches `dashboard_live/public/live-data/`. Cannot
contaminate the on-stage demo. Every output file the script writes
sits under a tempdir and is cleaned up on exit.

Honesty constraints (mirrored from
`docs/runtime_correction_preview_design.md`):
- Every synthetic proposal carries `preview_only=true, applied=false`.
- The script does **not** boot xv6 and does **not** claim any
  correction was applied to xv6.

Usage:
    python3 scripts/correction_preview_smoke.py
    python3 scripts/correction_preview_smoke.py --keep-tmp
    python3 scripts/correction_preview_smoke.py --recommendation \\
        dashboard_live/public/live-data/recommendation.json

    # Also exercise the LLM-driven proposer (requires UPSTAGE_API_KEY in .env):
    python3 scripts/correction_preview_smoke.py --mode llm
    python3 scripts/correction_preview_smoke.py --mode both

Exit codes:
    0 — every scenario produced a proposer + guard result (accepted or
        rejected — both are valid outcomes; the smoke just proves the
        path runs).
    1 — at least one scenario failed to produce a file or returned a
        non-zero from the proposer/guard.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT / "tools"

# One synthetic event per detector type, mirroring the severity
# rankings the proposer's rule table relies on.
SCENARIOS = [
    {
        "name": "starvation",
        "events": [{"tick": 32, "type": "starvation", "pid": 5,
                    "detail": "synthetic — pid 5 waited 50 ticks", "severity": "high"}],
    },
    {
        "name": "high_response_time",
        "events": [{"tick": 24, "type": "high_response_time", "pid": -1,
                    "detail": "synthetic — avg_response_time=15 above threshold 10",
                    "severity": "medium"}],
    },
    {
        "name": "high_preemption_rate",
        "events": [{"tick": 60, "type": "high_preemption_rate", "pid": -1,
                    "detail": "synthetic — 30 preempts in 50 ticks (0.60/tick)",
                    "severity": "low"}],
    },
    {
        "name": "low_throughput",
        "events": [{"tick": 100, "type": "low_throughput", "pid": -1,
                    "detail": "synthetic — throughput=0.02 below threshold 0.05",
                    "severity": "medium"}],
    },
    {
        "name": "multi_event (starvation outranks)",
        "events": [
            {"tick": 32, "type": "starvation", "pid": 5,
             "detail": "synthetic", "severity": "high"},
            {"tick": 40, "type": "high_response_time", "pid": -1,
             "detail": "synthetic", "severity": "medium"},
        ],
    },
]

DEFAULT_RECOMMENDATION = ROOT / "dashboard_live" / "public" / "live-data" / "recommendation.json"

FALLBACK_RECOMMENDATION = {
    "algorithm": "MLFQ",
    "recommended_scheduling_algorithm": "MLFQ",
    "target_metric": "avg_response_time",
    "params": {"queues": 2, "quantum": [10, 50],
               "aging_threshold": 500, "boost_interval": 100},
}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _run(cmd: list[str]) -> int:
    print("  $ " + " ".join(cmd))
    return subprocess.run(cmd, capture_output=False).returncode


def run_scenario(name: str, events: list[dict], rec: dict,
                 tmp_root: Path, mode: str) -> dict:
    """Run one scenario through proposer (in `mode`) + guard.

    `mode` is 'deterministic' or 'llm'; the LLM path requires
    UPSTAGE_API_KEY in .env and gracefully degrades to deterministic
    inside the proposer itself if the API call fails.
    """
    label = f"{name}__{mode}".replace(" ", "_").replace("(", "").replace(")", "")
    sandbox = tmp_root / label
    sandbox.mkdir(parents=True, exist_ok=True)
    events_path = sandbox / "runtime_events.json"
    rec_path = sandbox / "recommendation.json"
    proposal_path = sandbox / "correction_proposal.json"
    decision_path = sandbox / "correction_guard_decision.json"

    events_path.write_text(json.dumps({"total_problems": len(events),
                                       "events": events}, indent=2))
    rec_path.write_text(json.dumps(rec, indent=2))

    proposer_cmd = [sys.executable, str(TOOLS_DIR / "correction_proposer.py"),
                    "--events", str(events_path),
                    "--recommendation", str(rec_path),
                    "--out", str(proposal_path),
                    "--mode", mode]
    rc = _run(proposer_cmd)
    result: dict = {"name": name, "mode": mode, "proposer_rc": rc}
    if rc != 0 or not proposal_path.is_file():
        result["status"] = "PROPOSER FAILED"
        return result

    proposal = _read_json(proposal_path)
    result["preview_only"] = proposal.get("preview_only") is True
    result["applied"] = proposal.get("applied")
    proposed = proposal.get("proposed") or {}
    result["correction_type"] = proposed.get("correction_type")
    result["new_algo"] = proposed.get("new_scheduling_algorithm")
    result["rationale"] = proposed.get("rationale")
    # Record which mode actually produced the proposal — the proposer
    # may have fallen back from llm -> deterministic on a Solar error.
    result["effective_mode"] = (proposal.get("_meta") or {}).get("mode", mode)

    rc = _run([sys.executable, str(TOOLS_DIR / "correction_guard.py"),
               "--proposal", str(proposal_path),
               "--out", str(decision_path)])
    result["guard_rc"] = rc
    if rc != 0 or not decision_path.is_file():
        result["status"] = "GUARD FAILED"
        return result

    decision = _read_json(decision_path)
    result["guard_result"] = decision.get("guard_result")
    result["guard_reason"] = decision.get("reason")
    result["status"] = "OK"
    return result


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Exercise correction_proposer + correction_guard on synthetic events"
    )
    ap.add_argument("--recommendation", default=str(DEFAULT_RECOMMENDATION),
                    help="recommendation.json to use as the current algo/params "
                         "(default: committed live-data; falls back to a baked MLFQ "
                         "recommendation if absent)")
    ap.add_argument("--keep-tmp", action="store_true",
                    help="do not delete the temp directory at exit (useful for "
                         "inspecting the proposal/decision JSON)")
    ap.add_argument("--mode", choices=["deterministic", "llm", "both"],
                    default="deterministic",
                    help="proposer mode to exercise: 'deterministic' (default, "
                         "no API key needed), 'llm' (requires UPSTAGE_API_KEY), "
                         "or 'both' (runs each scenario twice for comparison)")
    args = ap.parse_args()

    rec_path = Path(args.recommendation)
    if rec_path.is_file():
        rec = _read_json(rec_path)
        rec_source = str(rec_path)
    else:
        rec = FALLBACK_RECOMMENDATION
        rec_source = "(baked default — recommendation.json absent)"

    modes = ["deterministic", "llm"] if args.mode == "both" else [args.mode]

    print(f"recommendation source: {rec_source}")
    print(f"scenarios: {len(SCENARIOS)} × mode(s): {modes}")
    print()

    tmp_root = Path(tempfile.mkdtemp(prefix="correction_preview_smoke_"))
    try:
        results = []
        for m in modes:
            for s in SCENARIOS:
                print(f"--- scenario: {s['name']} [mode={m}] ---")
                results.append(run_scenario(s["name"], s["events"], rec, tmp_root, m))
                print()

        print("=" * 90)
        print("summary")
        print("=" * 90)
        header = (f"{'scenario':<32} {'mode':<13} {'status':<14} "
                  f"{'correction':<22} {'algo':<8} {'guard':<10}")
        print(header)
        print("-" * len(header))
        all_ok = True
        for r in results:
            ok = r.get("status") == "OK"
            all_ok = all_ok and ok and (r.get("preview_only") is True) and (r.get("applied") is False)
            mode_label = r.get("mode", "?")
            eff = r.get("effective_mode")
            if eff and eff != mode_label:
                mode_label = f"{mode_label}→{eff}"  # fallback indicator
            print(f"{r['name'][:32]:<32} {mode_label:<13} {r['status']:<14} "
                  f"{str(r.get('correction_type','—'))[:22]:<22} "
                  f"{str(r.get('new_algo','—'))[:8]:<8} "
                  f"{str(r.get('guard_result','—'))[:10]:<10}")

        print()
        print(f"tmpdir: {tmp_root}")
        if args.keep_tmp:
            print("(kept — inspect JSON files inside per-scenario dirs)")
        else:
            shutil.rmtree(tmp_root, ignore_errors=True)

        print()
        print("Honesty:")
        print("  - Every proposal/decision is preview_only=true / applied=false.")
        print("  - Nothing was applied to xv6. No CORRECTION_APPLIED event was emitted.")
        print("  - dashboard_live/public/live-data/ was NOT touched.")
        return 0 if all_ok else 1
    finally:
        if args.keep_tmp:
            pass
        # We delete inside the try block above on success; on exception
        # the tmpdir is left behind for inspection.


if __name__ == "__main__":
    sys.exit(main())
