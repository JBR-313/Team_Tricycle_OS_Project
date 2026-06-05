"""Algorithm Guard regression tests — validation, clamping, fallback.

The guard is the safety layer between the LLM and xv6: it must clamp
out-of-range params, reject unimplemented algorithms, and never crash on
malformed input. These tests pin that behavior. Offline; no API key.
"""
import algorithm_guard as ag


# ── param clamping (normalize_params) ──────────────────────────────────────

def test_rr_quantum_in_range_kept():
    params, warnings = ag.normalize_params("RR", {"quantum": 5})
    assert params["quantum"] == 5
    assert warnings == []


def test_rr_quantum_out_of_range_clamped_to_default():
    # 0 and 9999 are both outside [1, 100] -> default 10, with a warning.
    for bad in (0, 9999, -3):
        params, warnings = ag.normalize_params("RR", {"quantum": bad})
        assert params["quantum"] == ag.DEFAULT_PARAMS["RR"]["quantum"]
        assert any("out of range" in w for w in warnings)


def test_rr_quantum_bool_rejected():
    # bool is not a valid int param even though True == 1 in Python.
    params, warnings = ag.normalize_params("RR", {"quantum": True})
    assert params["quantum"] == ag.DEFAULT_PARAMS["RR"]["quantum"]
    assert warnings


def test_fcfs_rejects_params():
    params, warnings = ag.normalize_params("FCFS", {"quantum": 4})
    assert params == {}
    assert any("does not accept parameters" in w for w in warnings)


def test_mlfq_quantum_length_must_match_queues():
    # queues=3 but quantum has 2 entries -> falls back to default quantum.
    params, warnings = ag.normalize_params(
        "MLFQ", {"queues": 3, "quantum": [2, 4]}
    )
    assert params["quantum"] == ag.DEFAULT_PARAMS["MLFQ"]["quantum"]
    assert any("length" in w for w in warnings)


def test_mlfq_quantum_valid_kept():
    params, _ = ag.normalize_params(
        "MLFQ", {"queues": 3, "quantum": [3, 6, 9]}
    )
    assert params["quantum"] == [3, 6, 9]
    assert params["queues"] == 3


def test_mlfq_queues_out_of_range_clamped():
    params, warnings = ag.normalize_params("MLFQ", {"queues": 99})
    assert params["queues"] == ag.DEFAULT_PARAMS["MLFQ"]["queues"]
    assert warnings


# ── SJF/SRTF predictor validation ──────────────────────────────────────────

def test_sjf_min_greater_than_max_resets_both():
    params, warnings = ag.normalize_params(
        "SJF", {"min": 50, "max": 10, "initial": 30}
    )
    assert params["min"] == ag.DEFAULT_PARAMS["SJF"]["min"]
    assert params["max"] == ag.DEFAULT_PARAMS["SJF"]["max"]
    assert any("min" in w and "max" in w for w in warnings)


def test_srtf_initial_clamped_into_range():
    # initial above max should be clamped to max (here max=20).
    params, warnings = ag.normalize_params(
        "SRTF", {"min": 1, "max": 20, "initial": 999}
    )
    assert params["initial"] == 20
    assert any("clamped" in w for w in warnings)


def test_sjf_alpha_out_of_range_uses_default():
    params, _ = ag.normalize_params("SJF", {"alpha_percent": 250})
    assert params["alpha_percent"] == ag.DEFAULT_PARAMS["SJF"]["alpha_percent"]


# ── algorithm rejection / fallback (guard) ─────────────────────────────────

def test_guard_accepts_valid_rr():
    decision = ag.guard({
        "algorithm": "RR",
        "params": {"quantum": 4},
        "target_metric": "avg_response_time",
        "reason": "round-robin fits the interactive workload",
    })
    assert decision["guard_result"] in ("accepted", "accepted_with_warning")
    assert decision["params"]["quantum"] == 4


def test_guard_rejects_unknown_algorithm_with_safe_fallback():
    decision = ag.guard({
        "algorithm": "QUANTUM_AI_9000",
        "target_metric": "avg_response_time",
        "reason": "made-up algorithm that is not implemented",
    })
    # Either an explicit rejection or a guard-chosen fallback, but never the
    # bogus algorithm and never a crash.
    chosen = (decision.get("scheduling_algorithm")
              or decision.get("algorithm")
              or decision.get("fallback_algorithm"))
    assert chosen != "QUANTUM_AI_9000"
    assert chosen in ag.DEFAULT_PARAMS  # a real, implemented algorithm


def test_guard_never_crashes_on_garbage_params():
    # params as a non-dict must not raise.
    decision = ag.guard({
        "algorithm": "RR",
        "params": "not-a-dict",
        "target_metric": "avg_response_time",
        "reason": "params intentionally malformed for this test",
    })
    assert "guard_result" in decision


def test_compatibility_score_bounds():
    score = ag.compatibility_score("MLFQ", "response_time")
    assert 0.0 <= score <= 1.0
    # unspecified metric is the neutral 0.5.
    assert ag.compatibility_score("RR", "unspecified") == 0.5
