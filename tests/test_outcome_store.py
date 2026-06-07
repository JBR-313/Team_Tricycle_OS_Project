"""Unit tests for tools/outcome_store.py — the measured-outcome retrieval memory.

Guards the honesty contract (no hidden-burst leakage into features) and the
leave-one-out correctness that the recommendation evaluation depends on: a
workload must never retrieve itself, and relevance weights must be computed only
from the records actually in the pool (no peeking at the held-out answer).

Fully offline: no API key, no QEMU.
"""
import json

import outcome_store as osm


def _summary(**over):
    base = {
        "process_count": 4, "avg_arrival_gap": 1.0,
        "cpu_bound_ratio": 0.0, "interactive_ratio": 0.5,
        "avg_priority": 5.0, "priority_variance": 0.0,
        "burst_count_distribution": {"min": 1, "max": 1, "avg": 1.0},
        "has_starvation_risk": False, "target_metric": "avg_response_time",
        "total_cpu_work": 999,  # MUST NOT leak into features
    }
    base.update(over)
    return base


# ── honesty: features carry no hidden-burst aggregate ────────────────────────
def test_features_exclude_total_cpu_work_and_answer_keys():
    feats = osm.prompt_safe_features(_summary())
    assert "total_cpu_work" not in feats
    assert "expected_best_algorithm" not in feats
    # the hidden aggregate value must not appear under any feature key
    assert 999 not in feats.values()
    # only the documented prompt-safe keys (+ target_metric) are present
    assert set(feats) == set(osm._NUMERIC_FEATURES) | {"target_metric"}


def test_format_examples_has_label_but_no_burst_durations():
    neighbors = [{
        "name": "x", "measured_best": "RR", "target_metric": "avg_response_time",
        "features": osm.prompt_safe_features(_summary()),
    }]
    text = osm.format_examples_for_prompt(neighbors)
    assert "MEASURED BEST ON xv6: RR" in text
    assert "999" not in text  # total_cpu_work never rendered


# ── leave-one-out retrieval correctness ──────────────────────────────────────
def _store():
    return [
        {"name": "a", "measured_best": "RR", "target_metric": "avg_response_time",
         "features": osm.prompt_safe_features(_summary(process_count=4, avg_priority=3))},
        {"name": "b", "measured_best": "MLFQ", "target_metric": "avg_response_time",
         "features": osm.prompt_safe_features(_summary(process_count=10, avg_priority=5))},
        {"name": "c", "measured_best": "MLFQ", "target_metric": "avg_response_time",
         "features": osm.prompt_safe_features(_summary(process_count=9, avg_priority=5))},
    ]


def test_retrieve_excludes_self():
    store = _store()
    got = osm.retrieve(store[0]["features"], store, k=3, exclude_name="a")
    assert all(r["name"] != "a" for r in got)
    assert len(got) == 2  # only b, c remain


def test_retrieve_orders_by_distance():
    store = _store()
    got = osm.retrieve(store[1]["features"], store, k=2, exclude_name="b")
    # b's nearest among {a, c} is c (both procs≈10, prio 5) not a (procs 4, prio 3)
    assert got[0]["name"] == "c"
    dists = [r["distance"] for r in got]
    assert dists == sorted(dists)


def test_knn_predict_returns_a_stored_label():
    store = _store()
    pred = osm.knn_predict(store[0]["features"], store, k=2, exclude_name="a")
    assert pred in {"RR", "MLFQ"}


# ── relevance weights are leakage-free (derived from the passed pool only) ────
def test_feature_weights_nonnegative_and_keyed():
    store = _store()
    w = osm.feature_weights(store)
    assert set(w) == set(osm._NUMERIC_FEATURES)
    assert all(v >= 0.0 for v in w.values())


def test_build_store_filters_by_source():
    xv6 = osm.build_store(source_filter="xv6-measured")
    assert xv6, "expected some xv6-measured workloads"
    assert all(r["source"] == "xv6-measured" for r in xv6)
    assert all(r["measured_best"] for r in xv6)
    # features must be leakage-free for every record
    for r in xv6:
        assert "total_cpu_work" not in r["features"]
