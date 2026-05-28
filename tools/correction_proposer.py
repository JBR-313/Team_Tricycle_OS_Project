#!/usr/bin/env python3
"""correction_proposer.py — deterministic runtime-correction proposal (PREVIEW ONLY).

Reads runtime_events.json (from tools/event_detector.py) and the current
recommendation.json, and writes a correction_proposal.json. The proposal is
preview_only=true / applied=false; nothing reaches xv6.

See docs/runtime_correction_preview_design.md for the schema and the rule
table this module implements.

Rule table (highest-severity event picks):

  starvation            -> aging_strengthen     (halve aging_threshold, floor 5)
  high_response_time    -> quantum_decrease     (halve top quantum, floor 2);
                                                 FCFS -> algorithm_change to RR
  high_preemption_rate  -> quantum_increase     (double top quantum, cap 100)
  low_throughput        -> parameter_update     (quantum up + boost_interval x1.5)

Usage:
    python3 tools/correction_proposer.py \\
        --events       outputs/runtime_events.json \\
        --recommendation outputs/recommendation.json \\
        --out          outputs/correction_proposal.json
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RULE_VERSION = 1

# severity -> integer rank, higher = picked first
SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}

# Caps mirror the existing algorithm_guard PARAM_RANGES so the new
# Correction Guard does not reject a proposal we built ourselves.
AGING_FLOOR = 5
QUANTUM_FLOOR = 2
QUANTUM_CEIL = 100
BOOST_CEIL = 10000


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _algo(rec: dict) -> str:
    """Canonical UPPER for rule comparison; preserve original casing for output."""
    return str(
        rec.get("recommended_scheduling_algorithm") or rec.get("algorithm") or "MLFQ"
    ).strip()


def _params(rec: dict) -> dict:
    return copy.deepcopy(rec.get("params") or {})


def _top_quantum_index(params: dict) -> int | None:
    """For MLFQ, top quantum is index 0 in the `quantum` list. For RR, the
    scalar `quantum` is the only one. Returns None if neither is present."""
    q = params.get("quantum")
    if isinstance(q, list) and q:
        return 0
    if isinstance(q, (int, float)):
        return -1  # sentinel: scalar quantum
    return None


def _apply_quantum(params: dict, factor: float, floor: int, ceil: int) -> dict:
    """Multiply the top quantum slot by factor, clamped to [floor, ceil].

    Mutates and returns params.
    """
    idx = _top_quantum_index(params)
    if idx is None:
        return params
    if idx == -1:
        new = max(floor, min(ceil, int(round(params["quantum"] * factor))))
        params["quantum"] = new
    else:
        params["quantum"] = list(params["quantum"])  # copy
        new = max(floor, min(ceil, int(round(params["quantum"][idx] * factor))))
        params["quantum"][idx] = new
    return params


def _pick_event(events: list[dict]) -> dict | None:
    if not events:
        return None
    return max(
        events,
        key=lambda e: (SEVERITY_RANK.get(e.get("severity", "low"), 0), -int(e.get("tick", 0))),
    )


def propose(events: list[dict], recommendation: dict) -> dict | None:
    """Return a correction_proposal dict, or None if no proposal is warranted."""
    triggering = _pick_event(events)
    if triggering is None:
        return None

    current_algo = _algo(recommendation)
    new_algo = current_algo
    params = _params(recommendation)
    etype = triggering.get("type", "")
    rationale_parts: list[str] = []
    correction_type: str

    if etype == "starvation":
        correction_type = "aging_strengthen"
        thr = params.get("aging_threshold")
        if isinstance(thr, (int, float)) and thr > 0:
            new_thr = max(AGING_FLOOR, int(thr) // 2)
            params["aging_threshold"] = new_thr
            rationale_parts.append(
                f"aging_threshold halved {thr} -> {new_thr} (floor {AGING_FLOOR})")
        else:
            params["aging_threshold"] = 50
            rationale_parts.append(
                "aging_threshold introduced at 50 (was absent or invalid)")

    elif etype == "high_response_time":
        if current_algo.upper() == "FCFS":
            correction_type = "algorithm_change"
            new_algo = "RR"
            params = {"quantum": 10}
            rationale_parts.append("FCFS suffers convoy effect on response time -> RR")
        else:
            correction_type = "quantum_decrease"
            idx = _top_quantum_index(params)
            if idx is None:
                params["quantum"] = 5
                rationale_parts.append("quantum introduced at 5 (was absent)")
            else:
                before = params["quantum"] if idx == -1 else params["quantum"][idx]
                _apply_quantum(params, 0.5, QUANTUM_FLOOR, QUANTUM_CEIL)
                after = params["quantum"] if idx == -1 else params["quantum"][idx]
                rationale_parts.append(
                    f"top-queue quantum halved {before} -> {after} (floor {QUANTUM_FLOOR})")

    elif etype == "high_preemption_rate":
        correction_type = "quantum_increase"
        idx = _top_quantum_index(params)
        if idx is None:
            params["quantum"] = 20
            rationale_parts.append("quantum introduced at 20 (was absent)")
        else:
            before = params["quantum"] if idx == -1 else params["quantum"][idx]
            _apply_quantum(params, 2.0, QUANTUM_FLOOR, QUANTUM_CEIL)
            after = params["quantum"] if idx == -1 else params["quantum"][idx]
            rationale_parts.append(
                f"top-queue quantum doubled {before} -> {after} (cap {QUANTUM_CEIL})")

    elif etype == "low_throughput":
        correction_type = "parameter_update"
        idx = _top_quantum_index(params)
        if idx is not None:
            before = params["quantum"] if idx == -1 else params["quantum"][idx]
            _apply_quantum(params, 1.5, QUANTUM_FLOOR, QUANTUM_CEIL)
            after = params["quantum"] if idx == -1 else params["quantum"][idx]
            rationale_parts.append(
                f"top-queue quantum x1.5 {before} -> {after} (cap {QUANTUM_CEIL})")
        bi = params.get("boost_interval")
        if isinstance(bi, (int, float)) and bi > 0:
            new_bi = min(BOOST_CEIL, int(round(bi * 1.5)))
            params["boost_interval"] = new_bi
            rationale_parts.append(f"boost_interval x1.5 {bi} -> {new_bi} (cap {BOOST_CEIL})")

    else:
        # Unknown event type -> no_op fallback so callers can still write a file.
        correction_type = "no_op"
        rationale_parts.append(f"no rule for event type {etype!r}")

    return {
        "preview_only": True,
        "applied": False,
        "current_scheduling_algorithm": current_algo,
        "triggered_by": list(events),
        "proposed": {
            "correction_type": correction_type,
            "new_scheduling_algorithm": new_algo,
            "new_params": params,
            "rationale": "; ".join(rationale_parts) or "no change",
            "triggering_event": triggering,
        },
        "_meta": {
            "source": "tools/correction_proposer.py",
            "generated_at": _iso_now(),
            "rule_version": RULE_VERSION,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Propose a preview-only runtime correction from runtime_events.json"
    )
    ap.add_argument("--events", required=True,
                    help="runtime_events.json from tools/event_detector.py")
    ap.add_argument("--recommendation", required=True,
                    help="recommendation.json from tools/llm_advisor.py")
    ap.add_argument("--out", required=True,
                    help="output correction_proposal.json")
    args = ap.parse_args()

    events_doc = _read_json(Path(args.events))
    events = events_doc.get("events") if isinstance(events_doc, dict) else None
    if not isinstance(events, list) or not events:
        print("[correction_proposer] no events -> no proposal written.")
        return 0

    rec = _read_json(Path(args.recommendation))
    proposal = propose(events, rec)
    if proposal is None:
        print("[correction_proposer] no proposal warranted (empty after filter).")
        return 0

    Path(args.out).write_text(json.dumps(proposal, indent=2) + "\n", encoding="utf-8")
    print(f"[correction_proposer] wrote {args.out}: "
          f"{proposal['proposed']['correction_type']} on "
          f"{proposal['proposed']['triggering_event'].get('type')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
