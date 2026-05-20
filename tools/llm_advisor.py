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
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Import the Solar Pro 3 client living next to this file (tools/).
try:
    from tools.solar_client import SolarClient, SolarError
except ImportError:  # when run as `python3 tools/llm_advisor.py`
    from solar_client import SolarClient, SolarError

ALGORITHMS = ["FCFS", "RR", "PRIORITY", "MLFQ"]

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
  - PRIORITY : Priority Scheduling + aging (low-priority starvation risk)
  - MLFQ     : Multi-Level Feedback Queue (favors interactive, aging possible)

You must also propose algorithm parameters. Schema per algorithm:
  - FCFS     : params = {{}}     (no parameters)
  - RR       : params = {{ "quantum": <int 1-100> }}                ticks per round
  - PRIORITY : params = {{ "aging_threshold": <int 1-10000> }}      ticks before aging
  - MLFQ     : params = {{
                 "queues": <int 2-5>,
                 "quantum": [<int 1-100>, ...]  (length = queues),
                 "aging_threshold": <int 1-10000>,
                 "boost_interval": <int 10-10000>
               }}

You are an ADVISOR only. You do not control the scheduler. Your job is to \
output a recommendation; another component will verify it by actually running \
the workload in xv6.

Respond with STRICT JSON only (no markdown, no prose outside JSON), with \
exactly these keys:
{{
  "algorithm": "<one of FCFS | RR | PRIORITY | MLFQ>",
  "params": {{ ... algorithm-specific, see schema above ... }},
  "reason": "<concise explanation, 2-4 sentences, referencing the workload>",
  "target_metric": "<one of waiting_time | response_time | turnaround_time | \
throughput | starvation>",
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
    # params is optional here — algorithm_guard.py will fill in defaults
    # and validate ranges. We just check the type.
    params = rec.get("params")
    if params is not None and not isinstance(params, dict):
        raise SolarError(f"'params' must be an object, got {type(params).__name__}.")
    rec.setdefault("params", {})
    return rec


# ---------------------------------------------------------------------------
# Feedback mode (Prompt Feedback Loop)
# ---------------------------------------------------------------------------
#
# Pipeline position (architecture_diagram.md W8):
#
#     evaluation_result.csv  -->  llm_advisor.py --mode feedback
#                                          |
#                                          v
#                              prompt_feedback_rules.md
#
# Trigger: Role A's evaluator.py writes "fail" rows when the advisor picked an
# algorithm clearly worse than the best one. "near-success" rows are accepted
# without prompt update.

FEEDBACK_SYSTEM_PROMPT = """You are the Prompt Feedback Generator for an \
LLM-based CPU scheduling advisor.

You receive a list of FAILED recommendations: cases where the advisor LLM \
picked algorithm A but evaluation later showed B would have been clearly \
better for the target metric.

Write concise prompt-engineering rules in Markdown that will be re-injected \
into the advisor's system prompt next time it runs. Each rule should:
  - begin with a condition tied to workload or metric characteristics
  - end with a directive ("prefer X over Y", "avoid X when ...", etc.)
  - be specific (cite the metric and the algorithm pair when possible)
  - avoid restating textbook algorithm definitions

Use a flat bullet list. No preamble, no closing remarks, no code fences.
"""

# Tolerate variation in column naming from Role A's evaluator.
_FAIL_VALUES = {"fail", "failed", "FAIL"}
_STATUS_KEYS = ("status", "result", "verdict", "outcome")
_SELECTED_KEYS = ("llm_selected", "recommended", "algorithm", "advisor_algorithm")
_BEST_KEYS = ("actual_best", "best", "best_algorithm", "ground_truth")
_METRIC_KEYS = ("target_metric", "metric")
_WORKLOAD_KEYS = ("workload_id", "workload", "id", "scenario")
_REGRET_KEYS = ("regret_score", "regret")


def _pick(row: dict, keys: tuple[str, ...], default: str = "?") -> str:
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            return str(v)
    return default


def read_fail_cases(csv_path: Path) -> list[dict]:
    if not csv_path.is_file():
        raise SystemExit(
            f"[feedback] evaluation_result.csv not found: {csv_path}\n"
            f"  Role A's evaluator.py must produce it first."
        )
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    fails = []
    for row in rows:
        status = _pick(row, _STATUS_KEYS, default="").strip().lower()
        if status in _FAIL_VALUES or status == "fail":
            fails.append(row)
    return fails


def build_feedback_user_prompt(fails: list[dict]) -> str:
    lines = ["Failed recommendations to learn from:\n"]
    for i, row in enumerate(fails, 1):
        lines.append(
            f"{i}. workload={_pick(row, _WORKLOAD_KEYS)} "
            f"target_metric={_pick(row, _METRIC_KEYS)} "
            f"llm_selected={_pick(row, _SELECTED_KEYS)} "
            f"actual_best={_pick(row, _BEST_KEYS)} "
            f"regret={_pick(row, _REGRET_KEYS)}"
        )
    lines.append(
        "\nProduce the Markdown rule list now. Group similar cases into one rule."
    )
    return "\n".join(lines)


def run_feedback(eval_csv: Path, rules_out: Path) -> int:
    fails = read_fail_cases(eval_csv)
    if not fails:
        print(
            f"[feedback] no fail rows in {eval_csv}; "
            f"prompt rules not updated (near-success / success accepted)."
        )
        return 0

    print(f"[feedback] found {len(fails)} fail case(s); querying Solar Pro 3...")
    try:
        client = SolarClient()
        rules_md = client.complete(
            prompt=build_feedback_user_prompt(fails),
            system=FEEDBACK_SYSTEM_PROMPT,
            temperature=0.2,
        )
    except SolarError as exc:
        raise SystemExit(f"[feedback] LLM error: {exc}")

    timestamp = datetime.now(timezone.utc).isoformat()
    header = (
        f"<!-- Generated by tools/llm_advisor.py (feedback mode) "
        f"at {timestamp} from {eval_csv.name} ({len(fails)} fail cases) -->\n\n"
    )
    rules_out.write_text(header + rules_md.strip() + "\n", encoding="utf-8")
    print(f"[feedback] wrote {len(fails)} fail case(s) → {rules_out}")
    return 0


# ---------------------------------------------------------------------------
# Advise mode (default — the original behavior)
# ---------------------------------------------------------------------------


def run_advise(in_path: Path, out_path: Path, feedback_path: Path) -> int:
    summary = read_workload_summary(in_path)
    system_prompt = build_system_prompt(feedback_path)
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
        "workload_summary": str(in_path),
    }

    out_path.write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"[llm_advisor] recommended {rec['algorithm']} "
        f"(target={rec.get('target_metric')}) -> {out_path}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM Scheduling Advisor (Role B)")
    parser.add_argument(
        "--mode",
        choices=["advise", "feedback"],
        default="advise",
        help="advise: recommend an algorithm; feedback: write rules from fail cases",
    )
    parser.add_argument(
        "--in",
        dest="in_path",
        default=str(PROJECT_ROOT / "workload_summary.json"),
        help="[advise] path to workload_summary.json",
    )
    parser.add_argument(
        "--out",
        dest="out_path",
        default=str(PROJECT_ROOT / "recommendation.json"),
        help="[advise] path to write recommendation.json",
    )
    parser.add_argument(
        "--feedback",
        dest="feedback_path",
        default=str(PROJECT_ROOT / "prompt_feedback_rules.md"),
        help="path to prompt_feedback_rules.md "
        "(advise: input if it exists; feedback: output)",
    )
    parser.add_argument(
        "--eval",
        dest="eval_path",
        default=str(PROJECT_ROOT / "evaluation_result.csv"),
        help="[feedback] path to evaluation_result.csv",
    )
    args = parser.parse_args()

    if args.mode == "feedback":
        return run_feedback(Path(args.eval_path), Path(args.feedback_path))
    return run_advise(
        Path(args.in_path), Path(args.out_path), Path(args.feedback_path)
    )


if __name__ == "__main__":
    sys.exit(main())
