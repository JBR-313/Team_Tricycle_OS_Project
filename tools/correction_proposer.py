"""Runtime Correction Proposer (rule-based, propose + validate only).

Pipeline position (see docs/runtime_correction_design.md):

    runtime_events.json (from event_detector.py)
        + guard_decision.json (current algorithm/params)
            -->  correction_proposer.py  -->  correction.json

This is the FIRST safe slice of the runtime-correction loop: it turns a detected
problem into a deterministic, guard-validated correction PROPOSAL. It does NOT
apply the correction to a running scheduler (the simulator/xv6 mid-run apply and
the CORRECTION_APPLIED trace remain Future Work — see the design doc). No LLM is
used here, so it works with no API key.

Run:
    python3 tools/correction_proposer.py \\
        --events outputs/live/runtime_events.json \\
        --guard  outputs/live/guard_decision.json \\
        --out    outputs/live/correction.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))

# Reuse existing helpers — do not duplicate or modify guard/schema logic.
from schema_compat import get_guard_algorithm, normalize_algorithm_name  # noqa: E402
try:
    from tools.algorithm_guard import (
        normalize_params, normalize_algorithm, SUPPORTED_ALGORITHMS, DEFAULT_PARAMS,
    )
except ImportError:  # when run as `python3 tools/correction_proposer.py`
    from algorithm_guard import (
        normalize_params, normalize_algorithm, SUPPORTED_ALGORITHMS, DEFAULT_PARAMS,
    )

_SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def pick_problem(events: list[dict]) -> dict | None:
    """Pick the most severe detected problem (ties: earliest tick)."""
    if not events:
        return None
    return sorted(
        events,
        key=lambda p: (-_SEVERITY_RANK.get(str(p.get("severity", "low")).lower(), 0),
                       p.get("tick", 0)),
    )[0]


def propose(problem: dict, cur_algo: str, cur_params: dict) -> tuple[str, dict, str]:
    """Deterministic rule: map a problem to (to_algorithm, params, reason).

    cur_algo is canonical UPPERCASE. Returns canonical UPPERCASE to_algorithm.
    """
    ptype = str(problem.get("type", ""))
    cur_params = cur_params or {}

    def mlfq_default():
        return dict(DEFAULT_PARAMS["MLFQ"])

    if ptype == "starvation":
        if cur_algo == "MLFQ":
            at = cur_params.get("aging_threshold", DEFAULT_PARAMS["MLFQ"]["aging_threshold"])
            bi = cur_params.get("boost_interval", DEFAULT_PARAMS["MLFQ"]["boost_interval"])
            params = dict(cur_params)
            params["aging_threshold"] = max(1, int(at * 2 // 3))
            params["boost_interval"] = max(10, int(bi * 4 // 5))
            return "MLFQ", params, "Aging too weak; lower aging_threshold/boost_interval to rescue starved process."
        if cur_algo == "PRIORITY":
            at = cur_params.get("aging_threshold", DEFAULT_PARAMS["PRIORITY"]["aging_threshold"])
            return "PRIORITY", {"aging_threshold": max(1, int(at * 2 // 3))}, "Strengthen priority aging to prevent starvation."
        return "MLFQ", mlfq_default(), "Switch to MLFQ (with aging) to prevent starvation under the current algorithm."

    if ptype == "high_response_time":
        if cur_algo == "RR":
            q = cur_params.get("quantum", 10)
            return "RR", {"quantum": max(1, int(q) // 2)}, "Shorten RR quantum to improve response time."
        if cur_algo == "MLFQ":
            return "MLFQ", dict(cur_params) or mlfq_default(), "Keep MLFQ; favors short interactive jobs for response time."
        return "MLFQ", mlfq_default(), "Switch to MLFQ to favor short jobs and improve response time."

    if ptype == "low_throughput":
        return "FCFS", {}, "Reduce context-switch overhead (FCFS) to raise throughput."

    if ptype == "high_preemption_rate":
        if cur_algo == "RR":
            q = cur_params.get("quantum", 10)
            return "RR", {"quantum": min(100, int(q) * 2)}, "Lengthen RR quantum to cut excessive preemptions."
        if cur_algo == "MLFQ":
            params = dict(cur_params)
            q = params.get("quantum")
            if isinstance(q, list) and q:
                params["quantum"] = [min(100, int(v) * 2) for v in q]
            return "MLFQ", params, "Lengthen MLFQ quanta to cut excessive preemptions."
        return cur_algo, dict(cur_params), "Keep current algorithm; preemption rate is inherent to it."

    # Unknown problem type → no change.
    return cur_algo, dict(cur_params), f"No rule for problem type {ptype!r}; keeping current algorithm."


def build_correction(problem: dict, cur_algo: str, cur_params: dict) -> dict:
    to_algo, params, reason = propose(problem, cur_algo, cur_params)

    # Guard validation: clamp params to valid ranges + confirm the algorithm is
    # supported. We never apply an invalid correction.
    norm_algo = normalize_algorithm(to_algo)
    guard_validated = norm_algo in SUPPORTED_ALGORITHMS
    if guard_validated:
        assert norm_algo is not None
        params, _warnings = normalize_params(norm_algo, params)
    else:
        # Fall back to the current algorithm if the proposal is unsupported.
        to_algo = cur_algo
        params = cur_params

    return {
        "correction_needed": True,
        "trigger": {
            "type": problem.get("type"),
            "tick": problem.get("tick"),
            "pid": problem.get("pid"),
            "severity": problem.get("severity"),
        },
        "from_algorithm": normalize_algorithm_name(cur_algo),
        "to_algorithm": normalize_algorithm_name(to_algo),
        "params": params,
        "apply_from_tick": int(problem.get("tick", 0)) + 1,
        "reason": reason,
        "source": "rule",
        "guard_validated": bool(guard_validated),
        "applied": False,  # apply step is Future Work (see design doc)
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Runtime Correction Proposer (rule-based)")
    ap.add_argument("--events", default=str(PROJECT_ROOT / "outputs" / "live" / "runtime_events.json"))
    ap.add_argument("--guard",  default=str(PROJECT_ROOT / "outputs" / "live" / "guard_decision.json"))
    ap.add_argument("--out",    default=str(PROJECT_ROOT / "outputs" / "live" / "correction.json"))
    args = ap.parse_args()

    events_doc = _read_json(Path(args.events))
    guard = _read_json(Path(args.guard))

    problems = events_doc.get("events", []) if isinstance(events_doc, dict) else (events_doc or [])
    cur_algo = normalize_algorithm(get_guard_algorithm(guard, default="RR")) or "RR"
    cur_params = (guard or {}).get("params", {}) or {}

    problem = pick_problem(problems)
    if problem is None:
        correction = {
            "correction_needed": False,
            "trigger": None,
            "from_algorithm": normalize_algorithm_name(cur_algo),
            "reason": "No scheduling problems detected; no correction proposed.",
            "source": "rule",
            "guard_validated": True,
            "applied": False,
        }
    else:
        correction = build_correction(problem, cur_algo, cur_params)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(correction, indent=2) + "\n", encoding="utf-8")

    if correction["correction_needed"]:
        print(f"[correction_proposer] {correction['trigger']['type']} @ tick "
              f"{correction['trigger']['tick']} -> {correction['to_algorithm']} "
              f"params={correction['params']} (guard_validated={correction['guard_validated']}) "
              f"-> {out_path}")
    else:
        print(f"[correction_proposer] no correction needed -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
