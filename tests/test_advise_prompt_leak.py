"""Locks the advise-prompt honesty contract (tools/llm_advisor.build_user_prompt).

The LLM must reason from VISIBLE features only. Every answer-key / ground-truth
field must be stripped before the summary reaches a prompt:
  - actual burst lengths and their sum (the no-future-burst rule)
  - the evaluation answer key (expected_best_algorithm / expected_behavior)
  - soft answer-tags that name the workload class outright
    (description, id, family, per-process label, and the workload_file path —
    "workloads/xv6_interactive.json" names the class exactly like id does).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import llm_advisor  # noqa: E402


def _summary():
    """A summary carrying every field that must NOT reach the prompt, with
    sentinel values that cannot collide with legitimate prompt content."""
    return {
        "process_count": 3,
        "avg_arrival_gap": 1.5,
        "cpu_bound_ratio": 0.33,
        "interactive_ratio": 0.67,
        "avg_priority": 5.0,
        "priority_variance": 0.0,
        "has_starvation_risk": False,
        "burst_count_distribution": {"min": 1, "max": 1, "avg": 1.0},
        "target_metric": "avg_response_time",
        # ── must be stripped ──
        "total_cpu_work": 31337,
        "expected_best_algorithm": "SENTINEL_BEST_ALGO",
        "expected_behavior": "SENTINEL_BEHAVIOR",
        "description": "SENTINEL_DESCRIPTION",
        "id": "SENTINEL_ID",
        "family": "SENTINEL_FAMILY",
        "workload_file": "workloads/SENTINEL_CLASS_NAME.json",
        "visible_processes": [
            {"pid": 1, "arrival_time": 0, "priority": 5,
             "burst_count": 1, "io_count": 2, "label": "SENTINEL_LABEL"},
        ],
    }


def test_prompt_strips_every_answer_key_field():
    prompt = llm_advisor.build_user_prompt(_summary())
    for sentinel in ("31337", "SENTINEL_BEST_ALGO", "SENTINEL_BEHAVIOR",
                     "SENTINEL_DESCRIPTION", "SENTINEL_ID", "SENTINEL_FAMILY",
                     "SENTINEL_CLASS_NAME", "workloads/", "SENTINEL_LABEL"):
        assert sentinel not in prompt, f"answer-key leaked into prompt: {sentinel}"


def test_prompt_keeps_visible_features():
    prompt = llm_advisor.build_user_prompt(_summary())
    for key in ("process_count", "avg_arrival_gap", "cpu_bound_ratio",
                "interactive_ratio", "avg_priority", "priority_variance",
                "has_starvation_risk", "burst_count_distribution",
                "target_metric", "visible_processes", "io_count"):
        assert key in prompt, f"visible feature missing from prompt: {key}"


def test_strip_keys_cover_the_documented_contract():
    assert {"total_cpu_work", "expected_best_algorithm", "expected_behavior",
            "description", "id", "family", "workload_file"} <= set(
        llm_advisor._PROMPT_STRIP_KEYS)
    assert "label" in llm_advisor._VISIBLE_PROCESS_STRIP_KEYS
