"""Regression tests for tools/schema_compat.py.

The schema-compat layer is the single place that reconciles old/new spellings
(tick vs time, algo vs algorithm, backend vs mode) across every producer and
consumer. These tests pin the contract so a rename in one module can't silently
desync the dashboard.
"""
import schema_compat as sc


def test_normalize_algo_canonical_uppercase():
    assert sc.normalize_algo("Priority") == "PRIORITY"
    assert sc.normalize_algo("mlfq") == "MLFQ"
    assert sc.normalize_algo("  srtf ") == "SRTF"


def test_normalize_algo_falsy_defaults_to_rr():
    assert sc.normalize_algo(None) == "RR"
    assert sc.normalize_algo("") == "RR"


def test_recommended_algorithm_new_and_legacy_keys():
    assert sc.get_recommended_algorithm(
        {"recommended_scheduling_algorithm": "Priority"}) == "PRIORITY"
    assert sc.get_recommended_algorithm({"algorithm": "mlfq"}) == "MLFQ"
    assert sc.get_recommended_algorithm(None) == "RR"


def test_guard_algorithm_new_and_legacy_keys():
    assert sc.get_guard_algorithm({"scheduling_algorithm": "srtf"}) == "SRTF"
    assert sc.get_guard_algorithm({"algorithm": "fcfs"}) == "FCFS"


def test_event_tick_prefers_tick_then_time():
    assert sc.get_event_tick({"tick": 12, "time": 99}) == 12
    assert sc.get_event_tick({"time": 7}) == 7
    assert sc.get_event_tick(None) is None


def test_backend_from_backend_field_and_legacy_mode():
    assert sc.get_backend({"backend": "XV6"}) == "xv6"
    assert sc.get_backend({"mode": "xv6-log"}) == "xv6"
    # Legacy data EXPLICITLY claiming the (removed) simulator is still reported
    # as such — but an empty/unknown manifest must read 'unknown', never default
    # to a backend that no longer exists.
    assert sc.get_backend({"mode": "simulator"}) == "simulator"
    assert sc.get_backend({}) == "unknown"
    assert sc.get_backend(None) == "unknown"


def test_target_metric_aliasing():
    assert sc.normalize_target_metric("response_time") == "avg_response_time"
    assert sc.normalize_target_metric("waiting_time") == "avg_waiting_time"
    assert sc.normalize_target_metric("turnaround_time") == "avg_turnaround_time"
    assert sc.normalize_target_metric(None) == "avg_response_time"


def test_higher_vs_lower_better():
    assert sc.is_higher_better_metric("throughput") is True
    assert sc.is_lower_better_metric("waiting_time") is True
    assert sc.is_higher_better_metric("waiting_time") is False


def test_display_form_round_trips():
    assert sc.normalize_algorithm_name("priority") == "Priority"
    assert sc.normalize_algorithm_name("MLFQ") == "MLFQ"
    assert sc.normalize_algorithm_name("rr") == "RR"
    assert sc.normalize_algorithm_name(None) == "RR"


def test_normalize_trace_event_fills_tick_and_algo():
    ev = sc.normalize_trace_event({"time": 7, "algorithm": "SJF"})
    assert ev["tick"] == 7
    assert ev["algo"] == "SJF"
    # default_algo applied when the event omits its own
    ev2 = sc.normalize_trace_event({"tick": 1}, default_algo="rr")
    assert ev2["algo"] == "RR"


def test_normalize_recommendation_keeps_both_keys():
    out = sc.normalize_recommendation({"algorithm": "mlfq",
                                       "target_metric": "response_time"})
    # The canonical display key is always (re)written...
    assert out["recommended_scheduling_algorithm"] == "MLFQ"
    # ...while a pre-existing legacy 'algorithm' is preserved verbatim
    # (setdefault only fills it when absent).
    assert out["algorithm"] == "mlfq"
    assert out["target_metric"] == "avg_response_time"
    # When 'algorithm' is absent it is back-filled with the display form.
    out2 = sc.normalize_recommendation(
        {"recommended_scheduling_algorithm": "srtf"})
    assert out2["algorithm"] == "SRTF"
