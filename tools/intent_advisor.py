#!/usr/bin/env python3
"""intent_advisor.py — map a NATURAL-LANGUAGE workload intent to a scheduling
config. This is the LLM's uncontested lane (docs/GOAL_semantic.md): no numeric
heuristic can read an operator's English description of what they want.

Unlike tools/llm_advisor.py (which reasons over numeric visible features), this
reads ONLY the human's words. It never sees actual bursts. Output is the same
recommendation schema the Algorithm Guard validates, so an intent can flow
straight into the existing pipeline.
"""
from __future__ import annotations

import json
from typing import Any

ALGORITHMS = ("RR", "FCFS", "PRIORITY", "MLFQ", "SJF", "SRTF")
METRICS = ("avg_response_time", "avg_turnaround_time",
           "avg_waiting_time", "throughput")

SYSTEM_PROMPT = (
    "You are a scheduling-configuration assistant for an xv6 teaching OS. The "
    "operator describes, in plain English, the WORKLOAD they will run and what "
    "they care about. Translate that intent into a scheduling configuration.\n\n"
    "Choose exactly one algorithm from: RR, FCFS, PRIORITY, MLFQ, SJF, SRTF.\n"
    "Pick the target_metric the intent implies, one of: avg_response_time, "
    "avg_turnaround_time, avg_waiting_time, throughput.\n\n"
    "Guidance (standard OS reasoning):\n"
    "- responsiveness / interactivity / low latency -> RR (small quantum) or MLFQ\n"
    "- batch / throughput / long CPU-bound jobs, nobody waiting -> FCFS or SJF\n"
    "- mixed short+long, keep short snappy without starving long -> MLFQ\n"
    "- strict importance levels but no permanent starvation -> PRIORITY (with aging)\n"
    "- shortest-job-first to cut average waiting -> SJF; preempt for shorter "
    "remaining work -> SRTF\n\n"
    "You reason ONLY from the operator's words. You do NOT know any process's true "
    "future CPU burst; never invent one. Return STRICT JSON, exactly:\n"
    '{"algorithm": "<one of the six>", "target_metric": "<one of the four>", '
    '"params": {<algorithm params, or {} to accept defaults>}, '
    '"reason": "<one or two sentences tying the choice to the stated intent>", '
    '"confidence": <0..1>}'
)


def build_intent_prompt(intent: str) -> str:
    return (
        "Operator workload intent (natural language):\n\n"
        f"\"\"\"\n{intent.strip()}\n\"\"\"\n\n"
        "Return the strict JSON scheduling configuration described in the system "
        "prompt."
    )


def recommend_from_intent(intent: str, client: Any) -> dict:
    """Elicit a scheduling config from a natural-language intent via Solar Pro 3.

    Returns a recommendation dict in the schema the Algorithm Guard expects
    (algorithm / target_metric / params / reason / confidence), plus a _meta tag.
    """
    rec = client.complete_json(
        prompt=build_intent_prompt(intent),
        system=SYSTEM_PROMPT,
        temperature=0.0,
    )
    algorithm = str(rec.get("algorithm", "")).strip().upper()
    out = {
        "algorithm": algorithm,
        "recommended_scheduling_algorithm": algorithm,
        "target_metric": rec.get("target_metric"),
        "params": rec.get("params") if isinstance(rec.get("params"), dict) else {},
        "reason": rec.get("reason", ""),
        "confidence": rec.get("confidence", None),
        "predicted_bursts": [],
        "_meta": {"source": "tools/intent_advisor.py",
                  "model": getattr(client, "model", "unknown"),
                  "input": "natural_language_intent"},
    }
    return out


if __name__ == "__main__":  # tiny manual smoke (needs UPSTAGE_API_KEY)
    import sys
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    from solar_client import SolarClient
    text = " ".join(sys.argv[1:]) or "Interactive desktop; responsiveness matters most."
    print(json.dumps(recommend_from_intent(text, SolarClient()), indent=2))
