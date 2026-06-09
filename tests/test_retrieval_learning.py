"""Regression tests for the retrieval-augmented learning loop (personalization
warm-start). Mirrors the opt-in shape of the feedback loop:

  1. build_retrieval_block — empty when no/blank store; injects precedents when
     the store has relevant outcomes; leave-one-out by name (no self-answer).
  2. Orchestrator advise command — default omits --retrieval-store;
     --use-retrieval (retrieval_store path) injects it.
  3. persist_outcome — appends a prompt-safe (features->measured_best) record,
     accumulates across runs, and skips honestly when best_algorithm is absent.

Fully offline — no UPSTAGE_API_KEY, no network, no QEMU. build_retrieval_block
only does feature math + file IO; the advise-command test stubs subprocess.run.
"""
import json
import sys
from pathlib import Path

import llm_advisor as la

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import orchestrator as orch  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────
def _features(*, procs=6.0, interactive=0.8, cpu=0.0, prio_var=0.0,
              target="avg_response_time"):
    return {"process_count": procs, "avg_arrival_gap": 1.0,
            "cpu_bound_ratio": cpu, "interactive_ratio": interactive,
            "avg_priority": 5.0, "priority_variance": prio_var,
            "burst_count_min": 1.0, "burst_count_max": 1.0,
            "burst_count_avg": 1.0, "starvation_risk": 0.0,
            "target_metric": target}


def _store(tmp_path, records):
    p = tmp_path / "outcome_store.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return p


def _summary(**kw):
    # workload_summary shape the analyzer emits; only the keys prompt_safe_features
    # reads matter here.
    f = _features(**kw)
    return {
        "id": "query_workload",
        "process_count": f["process_count"],
        "avg_arrival_gap": f["avg_arrival_gap"],
        "cpu_bound_ratio": f["cpu_bound_ratio"],
        "interactive_ratio": f["interactive_ratio"],
        "avg_priority": f["avg_priority"],
        "priority_variance": f["priority_variance"],
        "burst_count_distribution": {"min": 1, "max": 1, "avg": 1.0},
        "has_starvation_risk": False,
        "target_metric": f["target_metric"],
    }


# ── 1. build_retrieval_block ─────────────────────────────────────────────────
def test_retrieval_block_empty_when_no_store():
    assert la.build_retrieval_block(_summary(), None) == ""


def test_retrieval_block_empty_when_blank_store(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text("\n  \n", encoding="utf-8")
    assert la.build_retrieval_block(_summary(), p) == ""


def test_retrieval_block_injects_relevant_precedents(tmp_path):
    recs = [
        {"name": "past_a", "features": _features(interactive=0.8),
         "measured_best": "MLFQ", "target_metric": "avg_response_time"},
        {"name": "past_b", "features": _features(interactive=0.83),
         "measured_best": "MLFQ", "target_metric": "avg_response_time"},
        {"name": "past_c", "features": _features(cpu=1.0, interactive=0.0,
         target="avg_turnaround_time"), "measured_best": "FCFS",
         "target_metric": "avg_turnaround_time"},
    ]
    block = la.build_retrieval_block(_summary(interactive=0.8), _store(tmp_path, recs), k=2)
    assert "RETRIEVED PRECEDENTS" in block
    # nearest two to an interactive query are the MLFQ ones, not the FCFS one
    assert "MLFQ" in block
    assert block.count("MEASURED BEST") == 2


def test_retrieval_block_leaves_out_self(tmp_path):
    # A record sharing the query's id must never be retrieved (no self-answer).
    recs = [
        {"name": "query_workload", "features": _features(interactive=0.8),
         "measured_best": "SRTF", "target_metric": "avg_response_time"},
        {"name": "other", "features": _features(interactive=0.8),
         "measured_best": "MLFQ", "target_metric": "avg_response_time"},
    ]
    block = la.build_retrieval_block(_summary(interactive=0.8), _store(tmp_path, recs), k=5)
    assert "SRTF" not in block       # the self record is excluded
    assert "MLFQ" in block


# ── 2. orchestrator advise command: default vs --use-retrieval ───────────────
def _advise_cmd(tmp_path, monkeypatch, *, retrieval_store):
    (tmp_path / "workload_summary.json").write_text("{}", encoding="utf-8")

    captured = {}

    class _Res:
        returncode = 0

    def fake_run(cmd, *a, **k):
        captured["cmd"] = cmd
        (tmp_path / "recommendation.json").write_text("{}", encoding="utf-8")
        return _Res()

    monkeypatch.setattr(orch.subprocess, "run", fake_run)
    orch.run_advisor(tmp_path, dry_run=False, offline_fixture=False,
                     retrieval_store=retrieval_store)
    return captured["cmd"]


def test_default_advise_omits_retrieval_store(tmp_path, monkeypatch):
    cmd = _advise_cmd(tmp_path, monkeypatch, retrieval_store=None)
    assert "--retrieval-store" not in cmd


def test_use_retrieval_injects_store_path(tmp_path, monkeypatch):
    store = tmp_path / "outcome_store.jsonl"
    store.write_text("", encoding="utf-8")
    cmd = _advise_cmd(tmp_path, monkeypatch, retrieval_store=store)
    assert "--retrieval-store" in cmd
    i = cmd.index("--retrieval-store")
    assert cmd[i + 1].endswith("outcome_store.jsonl")


def test_use_retrieval_without_store_file_does_not_crash(tmp_path, monkeypatch):
    cmd = _advise_cmd(tmp_path, monkeypatch,
                      retrieval_store=tmp_path / "missing.jsonl")
    assert "--retrieval-store" in cmd


# ── 3. persist_outcome ───────────────────────────────────────────────────────
def _eval_dir(tmp_path, *, best="MLFQ"):
    out = tmp_path / "out"
    out.mkdir()
    (out / "workload_summary.json").write_text(json.dumps({
        "id": "wl1", "process_count": 5, "avg_arrival_gap": 2.0,
        "cpu_bound_ratio": 0.0, "interactive_ratio": 0.8, "avg_priority": 5.0,
        "priority_variance": 1.0,
        "burst_count_distribution": {"min": 1, "max": 1, "avg": 1.0},
        "has_starvation_risk": False, "target_metric": "avg_response_time",
    }), encoding="utf-8")
    metrics = {"scheduling_algorithm": "RR"}
    if best is not None:
        metrics["best_algorithm"] = best
    (out / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    return out


def test_persist_appends_prompt_safe_record(tmp_path):
    out = _eval_dir(tmp_path, best="MLFQ")
    store = tmp_path / "store.jsonl"
    orch.persist_outcome(out, store, dry_run=False)
    lines = [l for l in store.read_text().splitlines() if l.strip()]
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["measured_best"] == "MLFQ"
    assert rec["source"] == "xv6-measured"
    # prompt-safe: no leaked ground-truth aggregates
    assert "total_cpu_work" not in rec["features"]
    assert "actual_bursts" not in rec["features"]


def test_persist_accumulates(tmp_path):
    out = _eval_dir(tmp_path, best="MLFQ")
    store = tmp_path / "store.jsonl"
    orch.persist_outcome(out, store, dry_run=False)
    orch.persist_outcome(out, store, dry_run=False)
    assert len([l for l in store.read_text().splitlines() if l.strip()]) == 2


def test_persist_skips_when_no_best_algorithm(tmp_path):
    out = _eval_dir(tmp_path, best=None)
    store = tmp_path / "store.jsonl"
    orch.persist_outcome(out, store, dry_run=False)
    assert not store.exists()  # nothing written when comparison data is absent


def test_persist_dry_run_writes_nothing(tmp_path):
    out = _eval_dir(tmp_path, best="MLFQ")
    store = tmp_path / "store.jsonl"
    orch.persist_outcome(out, store, dry_run=True)
    assert not store.exists()
