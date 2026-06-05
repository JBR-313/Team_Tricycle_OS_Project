"""Regression tests for tools/event_detector.py.

The event detector watches a parsed trace + metrics and emits scheduling
problems that gate the runtime-correction loop. It must flag genuine
starvation / throughput / preemption / response-time issues, stay quiet on a
healthy run, sort by tick, and never crash on empty input.
"""
import event_detector as ed


def _healthy_metrics():
    return {
        "total_execution_time": 100,
        "preemption_count": 5,
        "throughput": 0.20,
        "avg_response_time": 3,
    }


def test_quiet_on_healthy_run():
    assert ed.detect([], _healthy_metrics()) == []


def test_starvation_flagged_when_gap_exceeds_threshold():
    gap = ed.STARVATION_THRESHOLD + 5
    events = [
        {"tick": 0, "pid": 1, "event": "ARRIVE"},
        {"tick": 0, "pid": 1, "event": "DISPATCH"},
        {"tick": gap, "pid": 1, "event": "PREEMPT"},
    ]
    problems = ed.detect(events, _healthy_metrics())
    assert any(p["type"] == "starvation" and p["pid"] == 1 for p in problems)


def test_no_starvation_when_gap_below_threshold():
    gap = ed.STARVATION_THRESHOLD - 1
    events = [
        {"tick": 0, "pid": 1, "event": "ARRIVE"},
        {"tick": 0, "pid": 1, "event": "DISPATCH"},
        {"tick": gap, "pid": 1, "event": "PREEMPT"},
    ]
    assert not any(p["type"] == "starvation"
                   for p in ed.detect(events, _healthy_metrics()))


def test_low_throughput_flagged():
    m = _healthy_metrics()
    m["throughput"] = ed.THRUPUT_THRESHOLD / 2
    assert any(p["type"] == "low_throughput"
               for p in ed.detect([], m))


def test_high_preemption_rate_flagged():
    m = _healthy_metrics()
    m["total_execution_time"] = 10
    m["preemption_count"] = 10  # 1.0/tick >> threshold
    assert any(p["type"] == "high_preemption_rate"
               for p in ed.detect([], m))


def test_high_response_time_flagged():
    m = _healthy_metrics()
    m["avg_response_time"] = ed.RESPONSE_THRESHOLD + 1
    assert any(p["type"] == "high_response_time"
               for p in ed.detect([], m))


def test_problems_sorted_by_tick():
    gap = ed.STARVATION_THRESHOLD + 1
    events = [
        {"tick": 0, "pid": 1, "event": "ARRIVE"},
        {"tick": 0, "pid": 1, "event": "DISPATCH"},
        {"tick": gap, "pid": 1, "event": "PREEMPT"},
    ]
    m = _healthy_metrics()
    m["avg_response_time"] = ed.RESPONSE_THRESHOLD + 1  # response problem at tick 0
    problems = ed.detect(events, m)
    ticks = [p["tick"] for p in problems]
    assert ticks == sorted(ticks)


def test_does_not_crash_on_empty_metrics():
    assert isinstance(ed.detect([], {}), list)
