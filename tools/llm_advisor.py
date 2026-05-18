"""LLM Scheduling Advisor (Role B).

Pipeline position (see architecture_diagram.md):

    workload_summary.json  -->  llm_advisor.py  -->  recommendation.json
                                      ^
                          prompt_feedback_rules.md (fail-only, if present)

What it does:
  1. Read `workload_summary.json` (produced by Role A's workload_analyzer.py).
  2. If `prompt_feedback_rules.md` exists, append it to the system prompt.
  3. Ask Upstage Solar Pro 3 to recommend ONE of:
         FCFS, RR, Priority, MLFQ
     and explain why, as strict JSON.
  4. Write the result to `recommendation.json`.

The LLM only advises. It does not control the scheduler — this script just
emits `recommendation.json`; algorithm_guard.py validates it downstream.

Usage:
    python3 tools/llm_advisor.py
    python3 tools/llm_advisor.py --in workload_summary.json \
        --out recommendation.json --feedback prompt_feedback_rules.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Import the Solar Pro 3 client living next to this file (tools/).
try:
    from tools.solar_client import SolarClient, SolarError
except ImportError:  # when run as `python3 tools/llm_advisor.py`
    from solar_client import SolarClient, SolarError

ALGORITHMS = ["FCFS", "RR", "Priority", "MLFQ"]

PROJECT_ROOT = Path(__file__).resolve().parent.parent

BASE_SYSTEM_PROMPT = f"""You are the LLM Scheduling Advisor for an xv6-based \
educational scheduler lab.

You are given a workload summary describing a set of processes (arrival time, \
CPU burst, priority, workload type, etc.). Recommend exactly ONE CPU \
scheduling algorithm that best fits this workload and the user's target \
metric.

You may ONLY choose from these algorithms:
  - FCFS     : First-Come First-Served (non-preemptive, simple, convoy effect)
  - RR       : Round Robin (preemptive, good response time, baseline)
  - Priority : Priority Scheduling (can starve low-priority processes)
  - MLFQ     : Multi-Level Feedback Queue (favors interactive, aging possible)

You are an ADVISOR only. You do not control the scheduler. Your job is to \
output a recommendation; another component will verify it by actually running \
the workload in xv6.

Respond with STRICT JSON only (no markdown, no prose outside JSON), with \
exactly these keys:
{{
  "algorithm": "<one of FCFS | RR | Priority | MLFQ>",
  "reason": "<concise explanation, 2-4 sentences, referencing the workload>",
  "target_metric": "<the scheduling metric this choice optimizes, e.g. \
waiting_time | response_time | turnaround_time | throughput | starvation>",
  "confidence": <number between 0 and 1>
}}
"""


def read_workload_summary(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(
            f"[llm_advisor] workload summary not found: {path}\n"
            f"  Role A's workload_analyzer.py must produce it first."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[llm_advisor] {path} is not valid JSON: {exc}")
    return data


def build_system_prompt(feedback_path: Path) -> str:
    prompt = BASE_SYSTEM_PROMPT
    if feedback_path.is_file():
        rules = feedback_path.read_text(encoding="utf-8").strip()
        if rules:
            prompt += (
                "\n\n--- ADDITIONAL RULES FROM PAST FAILURES "
                "(prompt_feedback_rules.md) ---\n"
                f"{rules}\n"
                "Follow these corrective rules carefully.\n"
            )
            print(f"[llm_advisor] applied feedback rules from {feedback_path}")
    return prompt


def build_user_prompt(summary: dict) -> str:
    return (
        "Here is the workload summary (JSON):\n\n"
        f"{json.dumps(summary, indent=2, ensure_ascii=False)}\n\n"
        "Recommend the single best scheduling algorithm for this workload "
        "and return the strict JSON object described in the system prompt."
    )


def validate(rec: dict) -> dict:
    if not isinstance(rec, dict):
        raise SolarError(f"Model returned non-object JSON: {rec!r}")
    algo = str(rec.get("algorithm", "")).strip()
    # Normalize common casing variants (e.g. "rr", "fcfs").
    match = next((a for a in ALGORITHMS if a.lower() == algo.lower()), None)
    if match is None:
        raise SolarError(
            f"Model recommended an unsupported algorithm: {algo!r}. "
            f"Must be one of {ALGORITHMS}."
        )
    rec["algorithm"] = match
    if not str(rec.get("reason", "")).strip():
        raise SolarError("Model did not provide a 'reason'.")
    rec.setdefault("target_metric", "unspecified")
    rec.setdefault("confidence", None)
    return rec


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM Scheduling Advisor (Role B)")
    parser.add_argument(
        "--in",
        dest="in_path",
        default=str(PROJECT_ROOT / "workload_summary.json"),
        help="path to workload_summary.json",
    )
    parser.add_argument(
        "--out",
        dest="out_path",
        default=str(PROJECT_ROOT / "recommendation.json"),
        help="path to write recommendation.json",
    )
    parser.add_argument(
        "--feedback",
        dest="feedback_path",
        default=str(PROJECT_ROOT / "prompt_feedback_rules.md"),
        help="optional prompt_feedback_rules.md (used only if it exists)",
    )
    args = parser.parse_args()

    summary = read_workload_summary(Path(args.in_path))
    system_prompt = build_system_prompt(Path(args.feedback_path))
    user_prompt = build_user_prompt(summary)

    try:
        client = SolarClient()  # reads UPSTAGE_API_KEY from .env
        print(f"[llm_advisor] querying Solar Pro 3 (model={client.model})...")
        rec = client.complete_json(
            prompt=user_prompt,
            system=system_prompt,
            temperature=0.0,
        )
        rec = validate(rec)
    except SolarError as exc:
        raise SystemExit(f"[llm_advisor] LLM error: {exc}")

    rec["_meta"] = {
        "source": "tools/llm_advisor.py",
        "model": client.model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workload_summary": str(Path(args.in_path)),
    }

    out_path = Path(args.out_path)
    out_path.write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"[llm_advisor] recommended {rec['algorithm']} "
        f"(target={rec.get('target_metric')}) -> {out_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
