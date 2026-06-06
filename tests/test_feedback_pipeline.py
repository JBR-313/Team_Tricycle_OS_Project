"""Regression tests for the safe feedback-loop closure.

Covers the four pillars of safe_feedback_loop_goal.md Phase 11:
  1. Rule parsing  — '- none' ignored, dedup, short-noise floor, FIFO cap.
  2. Trigger       — SUCCESS/NEAR-SUCCESS skip; FAIL / starvation generate.
  3. Orchestrator  — default advise command omits --feedback; --use-feedback
                     injects --feedback outputs/live/feedback_rules.md.
  4. Prompt static — FEEDBACK_SYSTEM_PROMPT carries the no-pid/no-tick
                     anti-overfit instruction.

All tests are fully offline — no UPSTAGE_API_KEY, no network, no QEMU. The
two paths that would call Solar Pro 3 (advise / feedback) are never reached:
the trigger tests assert the SKIP path (returns before the client) or stub
subprocess, and the command tests stub subprocess.run entirely.
"""
import sys
from pathlib import Path

import llm_advisor as la

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import orchestrator as orch  # noqa: E402


# ── 1. Rule parsing ──────────────────────────────────────────────────────────

def test_parse_ignores_none_sentinel():
    assert la.parse_rules_from_markdown("- none") == []
    assert la.parse_rules_from_markdown("- N/A\n- (none)") == []


def test_parse_drops_short_noise():
    # Below MIN_RULE_LEN is treated as noise.
    short = "- " + "x" * (la.MIN_RULE_LEN - 1)
    assert la.parse_rules_from_markdown(short) == []
    ok = "- " + "y" * la.MIN_RULE_LEN
    assert len(la.parse_rules_from_markdown(ok)) == 1


def test_parse_accepts_star_and_dash_bullets():
    md = "- this is a real rule about MLFQ\n* another genuine rule about FCFS"
    assert len(la.parse_rules_from_markdown(md)) == 2


def test_dedupe_is_case_insensitive_and_order_preserving():
    rules = ["Prefer MLFQ for interactive mixes",
             "prefer mlfq for interactive mixes",  # dup (casefold)
             "Avoid FCFS under convoy conditions"]
    out = la._dedupe_keep_order(rules)
    assert out == ["Prefer MLFQ for interactive mixes",
                   "Avoid FCFS under convoy conditions"]


def test_fifo_cap_keeps_most_recent():
    # Emulate the cap logic in run_feedback: keep the LAST MAX_RULES.
    combined = [f"rule number {i} about scheduling fairness" for i in
                range(la.MAX_RULES + 5)]
    capped = combined[-la.MAX_RULES:]
    assert len(capped) == la.MAX_RULES
    assert capped[0] == "rule number 5 about scheduling fairness"
    assert capped[-1].endswith(f"{la.MAX_RULES + 4} about scheduling fairness")


# ── 2. Trigger (SUCCESS / NEAR-SUCCESS skip; FAIL / starvation generate) ──────

def _write_metrics(tmp_path, judgment, *, starvation=False):
    import json
    p = tmp_path / "metrics.json"
    p.write_text(json.dumps({
        "judgment": judgment,
        "starvation_occurred": starvation,
        "scheduling_algorithm": "FCFS",
        "regret_score": 0.4,
    }), encoding="utf-8")
    return p


def test_feedback_skips_success(tmp_path):
    metrics = _write_metrics(tmp_path, "SUCCESS")
    rules = tmp_path / "feedback_rules.md"
    rc = la.run_feedback(str(metrics), rules, tmp_path / "rec.json")
    assert rc == 0
    assert not rules.exists()  # untouched on non-FAIL


def test_feedback_skips_near_success(tmp_path):
    metrics = _write_metrics(tmp_path, "NEAR-SUCCESS")
    rules = tmp_path / "feedback_rules.md"
    rc = la.run_feedback(str(metrics), rules, tmp_path / "rec.json")
    assert rc == 0
    assert not rules.exists()


def test_fail_verdicts_membership():
    assert "fail" in la.FAIL_VERDICTS
    assert "failed" in la.FAIL_VERDICTS
    assert "success" not in la.FAIL_VERDICTS
    assert "near-success" not in la.FAIL_VERDICTS


def _gen_calls(tmp_path, monkeypatch, judgment, *, starvation=False):
    """Run orchestrator.run_feedback_generator with subprocess stubbed; return
    the captured command list (or None if the LLM step was never reached)."""
    import json
    out_dir = tmp_path / "out"
    live_dir = tmp_path / "live"
    out_dir.mkdir()
    live_dir.mkdir()
    (out_dir / "metrics.json").write_text(json.dumps({
        "judgment": judgment, "starvation_occurred": starvation,
    }), encoding="utf-8")

    captured = {}

    class _Res:
        returncode = 0

    def fake_run(cmd, *a, **k):
        captured["cmd"] = cmd
        return _Res()

    monkeypatch.setattr(orch.subprocess, "run", fake_run)
    orch.run_feedback_generator(out_dir, live_dir,
                                offline_fixture=False, dry_run=False)
    return captured.get("cmd")


def test_generator_skips_on_success(tmp_path, monkeypatch):
    assert _gen_calls(tmp_path, monkeypatch, "SUCCESS") is None


def test_generator_skips_on_near_success(tmp_path, monkeypatch):
    assert _gen_calls(tmp_path, monkeypatch, "NEAR-SUCCESS") is None


def test_generator_fires_on_fail(tmp_path, monkeypatch):
    cmd = _gen_calls(tmp_path, monkeypatch, "FAIL")
    assert cmd is not None
    assert "--mode" in cmd and "feedback" in cmd


def test_generator_fires_on_starvation_even_if_not_fail(tmp_path, monkeypatch):
    cmd = _gen_calls(tmp_path, monkeypatch, "SUCCESS", starvation=True)
    assert cmd is not None


# ── 3. Orchestrator advise command: default vs --use-feedback ────────────────

def _advise_cmd(tmp_path, monkeypatch, *, use_feedback, make_rules=False):
    """Capture the command run_advisor builds, with subprocess stubbed so no
    real advisor runs. The stub writes recommendation.json so run_advisor sees
    success and returns without sys.exit."""
    out_dir = tmp_path
    (out_dir / "workload_summary.json").write_text("{}", encoding="utf-8")
    if make_rules:
        (out_dir / "feedback_rules.md").write_text(
            "- prefer MLFQ over FCFS for interactive mixes because response\n",
            encoding="utf-8")

    captured = {}

    class _Res:
        returncode = 0

    def fake_run(cmd, *a, **k):
        captured["cmd"] = cmd
        (out_dir / "recommendation.json").write_text("{}", encoding="utf-8")
        return _Res()

    monkeypatch.setattr(orch.subprocess, "run", fake_run)
    orch.run_advisor(out_dir, dry_run=False, offline_fixture=False,
                     use_feedback=use_feedback)
    return captured["cmd"]


def test_default_advise_omits_feedback(tmp_path, monkeypatch):
    cmd = _advise_cmd(tmp_path, monkeypatch, use_feedback=False)
    assert "--feedback" not in cmd


def test_use_feedback_injects_feedback_path(tmp_path, monkeypatch):
    cmd = _advise_cmd(tmp_path, monkeypatch, use_feedback=True, make_rules=True)
    assert "--feedback" in cmd
    i = cmd.index("--feedback")
    assert cmd[i + 1].endswith("feedback_rules.md")


def test_use_feedback_without_rules_file_does_not_crash(tmp_path, monkeypatch):
    # Missing rules file + --use-feedback must still build a valid command.
    cmd = _advise_cmd(tmp_path, monkeypatch, use_feedback=True, make_rules=False)
    assert "--feedback" in cmd


def test_parse_feedback_rules_counts_bullets(tmp_path):
    p = tmp_path / "feedback_rules.md"
    p.write_text("<!-- header -->\n- rule one about scheduling fairness\n"
                 "- none\n- rule two about convoy avoidance with FCFS\n",
                 encoding="utf-8")
    assert len(orch._parse_feedback_rules(p)) == 2


# ── 4. Prompt static check (anti-overfit) ────────────────────────────────────

def test_feedback_prompt_forbids_pid_and_tick_overfit():
    prompt = la.FEEDBACK_SYSTEM_PROMPT.lower()
    assert "pid" in prompt
    assert "tick" in prompt
    # The hard-constraint phrasing must be present, not just the words.
    assert "specific pid" in prompt
    assert "one-off" in prompt or "one off" in prompt


def test_feedback_prompt_requires_condition_directive_reason():
    prompt = la.FEEDBACK_SYSTEM_PROMPT.lower()
    assert "condition" in prompt
    assert "directive" in prompt
    assert "reason" in prompt
