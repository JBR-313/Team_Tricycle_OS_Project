"""Unit tests for tools/workload_analyzer.py — pipeline step [1].

The analyzer turns a workload JSON into workload_summary.json (the LLM's input).
Its honesty rule is critical: the per-process VISIBLE features it emits must
NEVER leak actual_bursts / cpu_bursts (the hidden ground truth the LLM must
predict, not read). Previously only an end-to-end subprocess test covered this;
these are direct unit tests of the metric math and the no-leak rule.

Fully offline: no API key, no QEMU.
"""
from pathlib import Path

from workload_analyzer import analyze_workload

_DUMMY_PATH = Path("workloads/_unit_test.json")


def _wl(processes, **meta):
    return {"processes": processes, **meta}


def _p(pid, arrival, bursts, priority=5, label="cpu_bound"):
    return {"pid": pid, "arrival_time": arrival, "actual_bursts": list(bursts),
            "priority": priority, "label": label}


# ── core metric math ─────────────────────────────────────────────────────────
def test_basic_counts_and_totals():
    wl = _wl([_p(1, 0, [3, 2]), _p(2, 5, [4]), _p(3, 10, [1])])
    s = analyze_workload(wl, _DUMMY_PATH)
    assert s["process_count"] == 3
    assert s["total_cpu_work"] == 3 + 2 + 4 + 1
    assert s["burst_count_distribution"] == {"min": 1, "max": 2, "avg": round(4 / 3, 2)}


def test_avg_arrival_gap():
    wl = _wl([_p(1, 0, [1]), _p(2, 4, [1]), _p(3, 10, [1])])
    s = analyze_workload(wl, _DUMMY_PATH)
    # gaps between sorted arrivals 0,4,10 -> (4, 6) -> mean 5.0
    assert s["avg_arrival_gap"] == 5.0


def test_single_process_gap_is_zero():
    s = analyze_workload(_wl([_p(1, 0, [5])]), _DUMMY_PATH)
    assert s["avg_arrival_gap"] == 0.0
    assert s["priority_variance"] == 0.0


def test_label_ratios():
    wl = _wl([_p(1, 0, [1], label="cpu_bound"),
              _p(2, 0, [1], label="interactive"),
              _p(3, 0, [1], label="interactive"),
              _p(4, 0, [1], label="cpu_bound")])
    s = analyze_workload(wl, _DUMMY_PATH)
    assert s["cpu_bound_ratio"] == 0.5
    assert s["interactive_ratio"] == 0.5


def test_priority_stats_and_starvation_risk():
    # priority range 2..9: 9 >= 2*3 -> starvation risk True
    wl = _wl([_p(1, 0, [1], priority=2), _p(2, 0, [1], priority=9)])
    s = analyze_workload(wl, _DUMMY_PATH)
    assert s["avg_priority"] == 5.5
    assert s["has_starvation_risk"] is True

    # narrow range 4..5: 5 < 4*3 -> no starvation risk
    wl2 = _wl([_p(1, 0, [1], priority=4), _p(2, 0, [1], priority=5)])
    assert analyze_workload(wl2, _DUMMY_PATH)["has_starvation_risk"] is False


def test_meta_passthrough():
    wl = _wl([_p(1, 0, [1])], expected_best_algorithm="RR",
             target_metric="avg_turnaround_time", id="demo")
    s = analyze_workload(wl, _DUMMY_PATH)
    assert s["expected_best_algorithm"] == "RR"
    assert s["target_metric"] == "avg_turnaround_time"
    assert s["id"] == "demo"


# ── HONESTY: visible features must not leak the hidden ground-truth bursts ────
def test_visible_processes_do_not_leak_actual_bursts():
    wl = _wl([_p(1, 0, [7, 3], priority=2, label="cpu_bound")])
    s = analyze_workload(wl, _DUMMY_PATH)
    vp = s["visible_processes"][0]
    # burst_count (a count) is allowed; the actual durations are NOT.
    assert vp["burst_count"] == 2
    assert "actual_bursts" not in vp
    assert "cpu_bursts" not in vp
    assert "bursts" not in vp
    # no value in the visible dict may equal the hidden burst list/values
    assert 7 not in vp.values()
    assert [7, 3] not in vp.values()


def test_summary_contains_no_actual_bursts_anywhere():
    wl = _wl([_p(1, 0, [42]), _p(2, 3, [99])])
    s = analyze_workload(wl, _DUMMY_PATH)
    import json
    blob = json.dumps(s)
    assert "actual_bursts" not in blob
    assert "cpu_bursts" not in blob
    # the distinctive hidden magnitudes must not appear in the summary
    assert "42" not in blob and "99" not in blob
