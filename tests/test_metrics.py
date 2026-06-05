"""Metrics regression tests — judgment thresholds, regret, trace-derived stats.

Pins the SUCCESS/NEAR/FAIL boundaries and the invariant that a well-formed
trace never yields a negative response time. Offline; no API key.
"""
import metrics as M


# ── judgment thresholds ────────────────────────────────────────────────────

def test_judgment_success_at_and_below_threshold():
    assert M.compute_judgment(0.0, False) == "SUCCESS"
    assert M.compute_judgment(M.SUCCESS_REGRET, False) == "SUCCESS"


def test_judgment_near_success_band():
    just_over = M.SUCCESS_REGRET + 0.01
    assert M.compute_judgment(just_over, False) == "NEAR-SUCCESS"
    assert M.compute_judgment(M.NEAR_SUCCESS_REGRET, False) == "NEAR-SUCCESS"


def test_judgment_fail_above_near_threshold():
    assert M.compute_judgment(M.NEAR_SUCCESS_REGRET + 0.01, False) == "FAIL"
    assert M.compute_judgment(1.0, False) == "FAIL"


def test_starvation_forces_fail_even_at_zero_regret():
    assert M.compute_judgment(0.0, True) == "FAIL"


# ── regret ─────────────────────────────────────────────────────────────────

def test_regret_zero_when_matching_best():
    # lower-is-better metric: llm == best in the comparison -> no regret.
    # baseline is a {algo: metrics} comparison map.
    r = M.compute_regret("avg_waiting_time", 10.0, {"RR": {"avg_waiting_time": 10.0}})
    assert r == 0.0 or abs(r) < 1e-9


def test_regret_positive_when_worse_than_best():
    # llm worse (higher waiting) than the best comparison algorithm.
    r = M.compute_regret("avg_waiting_time", 20.0, {"RR": {"avg_waiting_time": 10.0}})
    assert r > 0


def test_regret_none_without_baseline():
    assert M.compute_regret("avg_waiting_time", 20.0, {}) is None


# ── trace-derived stats ────────────────────────────────────────────────────

def _simple_trace():
    # Two processes, RR-ish. p1 arrives@0 runs 0-2 exits@2; p2 arrives@0
    # first dispatched@2 exits@4. No negative response times possible.
    return [
        {"tick": 0, "algo": "RR", "event": "ARRIVE", "pid": 1, "state": "RUNNABLE"},
        {"tick": 0, "algo": "RR", "event": "ARRIVE", "pid": 2, "state": "RUNNABLE"},
        {"tick": 0, "algo": "RR", "event": "DISPATCH", "pid": 1, "state": "RUNNING"},
        {"tick": 2, "algo": "RR", "event": "PREEMPT", "pid": 1, "state": "RUNNABLE"},
        {"tick": 2, "algo": "RR", "event": "DISPATCH", "pid": 2, "state": "RUNNING"},
        {"tick": 2, "algo": "RR", "event": "EXIT", "pid": 1, "state": "ZOMBIE",
         "turnaround": 2, "waiting": 0, "response": 0},
        {"tick": 4, "algo": "RR", "event": "EXIT", "pid": 2, "state": "ZOMBIE",
         "turnaround": 4, "waiting": 2, "response": 2},
    ]


def test_compute_metrics_basic_shape():
    m = M.compute_metrics(_simple_trace())
    assert m["process_count"] >= 2
    assert m["avg_response_time"] is not None
    assert m["avg_response_time"] >= 0
    assert m["avg_waiting_time"] >= 0


def test_no_negative_response_time_for_valid_trace():
    m = M.compute_metrics(_simple_trace())
    for p in m.get("per_process", []):
        rt = p.get("response_time")
        if isinstance(rt, (int, float)):
            assert rt >= 0, f"negative response time for pid {p.get('pid')}"


def test_preemption_count_from_trace():
    m = M.compute_metrics(_simple_trace())
    # exactly one PREEMPT event above.
    assert m["preemption_count"] == 1


def test_empty_trace_does_not_crash():
    m = M.compute_metrics([])
    # No EXIT events -> empty/falsy metrics, but must not raise.
    assert m == {} or m.get("process_count", 0) == 0
