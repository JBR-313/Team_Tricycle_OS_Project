"""Offline tests for the multi-seed robustness sweep (tools/seed_sweep.py)."""

import json

import seed_sweep as S


def _wl(tmp_path):
    wl = {
        "id": "sweep_demo",
        "target_metric": "avg_waiting_time",
        "processes": [
            {"pid": 1, "arrival_time": 0, "priority": 2,
             "cpu_bursts": [4], "actual_bursts": [4], "io_bursts": []},
            {"pid": 2, "arrival_time": 1, "priority": 5,
             "cpu_bursts": [8], "actual_bursts": [8], "io_bursts": []},
            {"pid": 3, "arrival_time": 2, "priority": 3,
             "cpu_bursts": [2], "actual_bursts": [2], "io_bursts": []},
        ],
    }
    p = tmp_path / "sweep_demo.json"
    p.write_text(json.dumps(wl), encoding="utf-8")
    return p


# ── parse_seeds ───────────────────────────────────────────────────────────────
def test_parse_seeds_range_inclusive():
    assert S.parse_seeds("1-5") == [1, 2, 3, 4, 5]


def test_parse_seeds_reversed_range_normalized():
    assert S.parse_seeds("5-1") == [1, 2, 3, 4, 5]


def test_parse_seeds_explicit_list():
    assert S.parse_seeds("3,1,9") == [3, 1, 9]


def test_parse_seeds_single():
    assert S.parse_seeds("7") == [7]


# ── _stats ──────────────────────────────────────────────────────────────────
def test_stats_basic():
    s = S._stats([2.0, 4.0, 6.0])
    assert s["mean"] == 4.0
    assert s["min"] == 2.0 and s["max"] == 6.0
    assert s["n"] == 3
    assert s["std"] > 0


def test_stats_single_sample_zero_std():
    s = S._stats([5.0])
    assert s["mean"] == 5.0
    assert s["std"] == 0.0


def test_stats_empty():
    s = S._stats([])
    assert s["mean"] is None and s["n"] == 0


# ── run (end-to-end on a tiny workload, no API) ────────────────────────────────
def test_run_aggregates_all_algorithms(tmp_path):
    res = S.run(_wl(tmp_path), [1, 2, 3], metric=None)
    assert res["seed_count"] == 3
    assert res["target_metric"] == "avg_waiting_time"
    # every algorithm that appears must carry stats + a best_count
    for algo, info in res["per_algorithm"].items():
        assert "target" in info and "best_count" in info
        assert info["target"]["n"] == 3
    # best-algorithm tally totals across seeds (each seed picks exactly one best)
    assert sum(res["best_algorithm_distribution"].values()) == 3


def test_run_is_deterministic(tmp_path):
    a = S.run(_wl(tmp_path), [1, 2, 3], metric=None)
    b = S.run(_wl(tmp_path), [1, 2, 3], metric=None)
    assert a["per_algorithm"] == b["per_algorithm"]
    assert a["best_algorithm_distribution"] == b["best_algorithm_distribution"]


def test_run_stability_fraction(tmp_path):
    res = S.run(_wl(tmp_path), [1, 2, 3, 4], metric=None)
    if res["most_frequent_best"]:
        wins = res["best_algorithm_distribution"][res["most_frequent_best"]]
        assert res["ranking_stability"] == round(wins / 4, 3)


def test_render_markdown_has_table(tmp_path):
    res = S.run(_wl(tmp_path), [1, 2], metric=None)
    md = S.render_markdown(res)
    assert "# Seed sweep" in md
    assert "best in N seeds" in md
