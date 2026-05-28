#!/usr/bin/env python3
"""correction_proposer.py — runtime-correction proposal (PREVIEW ONLY).

Reads runtime_events.json (from tools/event_detector.py) and the current
recommendation.json, and writes a correction_proposal.json. The proposal is
preview_only=true / applied=false; nothing reaches xv6.

Two modes share an identical output schema (correction_guard.py validates
both unchanged):

  --mode deterministic   (default)
      Hand-coded rule table — fast, reproducible, no API key needed.
      Rule table (highest-severity event picks):
        starvation           -> aging_strengthen   (halve aging_threshold)
        high_response_time   -> quantum_decrease   (halve top quantum);
                                                    FCFS -> RR
        high_preemption_rate -> quantum_increase   (double top quantum)
        low_throughput       -> parameter_update   (quantum + boost x1.5)

  --mode llm
      Ask Upstage Solar Pro 3 to propose the correction. Useful as the
      "LLM-driven runtime advisor" story. Falls back to deterministic if
      the LLM returns an unparseable / out-of-range proposal — the
      Correction Guard then ratifies whichever survived.

See docs/runtime_correction_preview_design.md for the schema.

Usage:
    python3 tools/correction_proposer.py \\
        --events         outputs/runtime_events.json \\
        --recommendation outputs/recommendation.json \\
        --out            outputs/correction_proposal.json
    python3 tools/correction_proposer.py --mode llm ...
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
            "mode": "deterministic",
        },
    }


# ---------------------------------------------------------------------------
# LLM mode (--mode llm)
# ---------------------------------------------------------------------------
#
# Same output schema as the deterministic path; the LLM picks the
# correction_type and new_params instead of the hand-coded rule table.
# correction_guard.py is unchanged — it re-validates whichever proposal
# arrived. If the LLM output is unparseable or out of range, we fall back
# to the deterministic proposal so the pipeline always produces something
# the Guard can examine.

ALLOWED_CORRECTION_TYPES = (
    "no_op",
    "algorithm_change",
    "parameter_update",
    "aging_strengthen",
    "quantum_decrease",
    "quantum_increase",
)

LLM_SYSTEM_PROMPT = """You are the Runtime Correction Advisor for an xv6 \
scheduler experiment.

You receive (1) the current scheduling recommendation that is RUNNING and \
(2) one or more runtime events the system observed (starvation, high \
response time, high preemption rate, low throughput, etc.). Propose ONE \
correction the scheduler could apply.

This is a PREVIEW only — your proposal will be re-validated by an algorithm \
guard and never applied to the kernel directly. Stay within the same \
supported algorithms (FCFS, RR, PRIORITY, MLFQ, SJF, SRTF) and the same \
param schema the original recommendation used.

Choose ONE correction_type from this set:
  - no_op             : the events do not warrant a change
  - algorithm_change  : switch to a different algorithm
  - parameter_update  : keep the algorithm, update multiple params
  - aging_strengthen  : reduce aging_threshold to counter starvation
  - quantum_decrease  : shrink top quantum to improve response time
  - quantum_increase  : grow top quantum to reduce preemption overhead

Respond with STRICT JSON only (no markdown, no code fences), exactly:
{
  "correction_type": "<one of the values above>",
  "new_scheduling_algorithm": "<FCFS|RR|PRIORITY|MLFQ|SJF|SRTF>",
  "new_params": { ... same schema the input recommendation used ... },
  "rationale": "<one sentence tying the events to the chosen correction>"
}
"""


def _llm_user_prompt(events: list[dict], rec: dict) -> str:
    return (
        "CURRENT RECOMMENDATION (running on xv6):\n"
        f"{json.dumps({k: rec.get(k) for k in ('algorithm', 'recommended_scheduling_algorithm', 'params', 'target_metric') if rec.get(k) is not None}, indent=2)}\n\n"
        f"RUNTIME EVENTS DETECTED ({len(events)}):\n"
        f"{json.dumps(events, indent=2)}\n\n"
        "Propose one correction now, as the JSON object described in the "
        "system prompt."
    )


def _build_proposal_from_llm(
    events: list[dict], recommendation: dict, llm_out: dict
) -> dict | None:
    """Validate the LLM's JSON enough to fit the correction_proposal schema.

    Returns a proposal dict on success, or None if the LLM output is unusable
    (the caller then falls back to the deterministic proposal).
    """
    if not isinstance(llm_out, dict):
        return None
    ctype = str(llm_out.get("correction_type", "")).strip()
    if ctype not in ALLOWED_CORRECTION_TYPES:
        return None
    new_algo = str(llm_out.get("new_scheduling_algorithm", "")).strip()
    if not new_algo:
        new_algo = _algo(recommendation)
    new_params = llm_out.get("new_params") or {}
    if not isinstance(new_params, dict):
        return None
    rationale = str(llm_out.get("rationale", "")).strip() or "LLM-proposed correction"
    triggering = _pick_event(events) or {}
    return {
        "preview_only": True,
        "applied": False,
        "current_scheduling_algorithm": _algo(recommendation),
        "triggered_by": list(events),
        "proposed": {
            "correction_type": ctype,
            "new_scheduling_algorithm": new_algo,
            "new_params": new_params,
            "rationale": rationale,
            "triggering_event": triggering,
        },
        "_meta": {
            "source": "tools/correction_proposer.py",
            "generated_at": _iso_now(),
            "rule_version": RULE_VERSION,
            "mode": "llm",
        },
    }


def propose_llm(events: list[dict], recommendation: dict) -> dict | None:
    """LLM-driven counterpart of propose(). Falls back to deterministic on
    any failure so the caller always gets a usable proposal (or None when
    even the deterministic path declines)."""
    # Local import keeps the deterministic path dependency-free for offline tests.
    try:
        from tools.solar_client import SolarClient, SolarError  # type: ignore
    except ImportError:  # when run as `python3 tools/correction_proposer.py`
        from solar_client import SolarClient, SolarError  # type: ignore[no-redef]

    try:
        client = SolarClient()
        llm_out = client.complete_json(
            prompt=_llm_user_prompt(events, recommendation),
            system=LLM_SYSTEM_PROMPT,
            temperature=0.0,
        )
    except SolarError as exc:
        print(f"[correction_proposer] LLM error ({exc}); falling back to deterministic.")
        return propose(events, recommendation)

    proposal = _build_proposal_from_llm(events, recommendation, llm_out)
    if proposal is None:
        print(
            "[correction_proposer] LLM proposal unparseable / out of range; "
            "falling back to deterministic."
        )
        return propose(events, recommendation)
    return proposal


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
    ap.add_argument("--mode", choices=["deterministic", "llm"],
                    default="deterministic",
                    help="deterministic rule table (default) or LLM-driven "
                    "proposal via Solar Pro 3; both produce the same schema")
    args = ap.parse_args()

    events_doc = _read_json(Path(args.events))
    events = events_doc.get("events") if isinstance(events_doc, dict) else None
    if not isinstance(events, list) or not events:
        print("[correction_proposer] no events -> no proposal written.")
        return 0

    rec = _read_json(Path(args.recommendation))
    if args.mode == "llm":
        proposal = propose_llm(events, rec)
    else:
        proposal = propose(events, rec)
    if proposal is None:
        print("[correction_proposer] no proposal warranted (empty after filter).")
        return 0

    Path(args.out).write_text(json.dumps(proposal, indent=2) + "\n", encoding="utf-8")
    print(f"[correction_proposer] wrote {args.out}: "
          f"{proposal['proposed']['correction_type']} on "
          f"{proposal['proposed']['triggering_event'].get('type')} "
          f"[mode={args.mode}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
