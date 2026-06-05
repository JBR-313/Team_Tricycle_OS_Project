"""Regression tests for tools/correction_guard.py.

The correction guard is the honesty gate for runtime-correction proposals:
it must (a) refuse anything not explicitly marked preview_only/applied=false,
(b) accept no-op proposals trivially, (c) reject unsupported algorithms and
out-of-range params with a no_op fallback, and (d) never raise on garbage.
"""
import correction_guard as cg


def _preview(proposed):
    return {"preview_only": True, "applied": False, "proposed": proposed}


def test_rejects_non_preview_proposal():
    # Missing the preview_only/applied=false marker => refused outright.
    d = cg.validate({"proposed": {"correction_type": "no_op"}})
    assert d["guard_result"] == "rejected"
    assert d["applied"] is False
    assert d["preview_only"] is True


def test_rejects_proposal_claiming_applied():
    d = cg.validate({"preview_only": True, "applied": True,
                     "proposed": {"correction_type": "no_op"}})
    assert d["guard_result"] == "rejected"


def test_no_op_is_trivially_accepted():
    d = cg.validate(_preview({"correction_type": "no_op"}))
    assert d["guard_result"] == "accepted"
    assert d["applied"] is False


def test_switch_to_supported_algo_accepted():
    d = cg.validate(_preview({
        "correction_type": "switch_algorithm",
        "new_scheduling_algorithm": "MLFQ",
        "new_params": {},
    }))
    assert d["guard_result"] == "accepted"
    assert d["new_scheduling_algorithm"] == "MLFQ"


def test_unsupported_algo_rejected_with_fallback():
    d = cg.validate(_preview({
        "correction_type": "switch_algorithm",
        "new_scheduling_algorithm": "QUANTUM_AI",
        "new_params": {},
    }))
    assert d["guard_result"] == "rejected"
    assert "new_scheduling_algorithm" in d["rejected_params"]
    # A rejected correction must leave xv6 unaffected (no_op fallback).
    assert d["fallback"]["correction_type"] == "no_op"


def test_out_of_range_rr_quantum_rejected():
    d = cg.validate(_preview({
        "correction_type": "tune_params",
        "new_scheduling_algorithm": "RR",
        "new_params": {"quantum": 9999},
    }))
    assert d["guard_result"] == "rejected"
    assert "quantum" in d["rejected_params"]


def test_in_range_rr_quantum_accepted():
    d = cg.validate(_preview({
        "correction_type": "tune_params",
        "new_scheduling_algorithm": "RR",
        "new_params": {"quantum": 4},
    }))
    assert d["guard_result"] == "accepted"


def test_never_crashes_on_garbage():
    for junk in [{}, {"preview_only": True, "applied": False},
                 {"preview_only": True, "applied": False, "proposed": None},
                 {"preview_only": True, "applied": False,
                  "proposed": {"new_scheduling_algorithm": None}}]:
        d = cg.validate(junk)
        assert isinstance(d, dict)
        assert d["applied"] is False  # never silently "applies"


def test_decision_always_marks_preview_and_unapplied():
    # Whatever the verdict, the decision must never claim to be live.
    for proposed in [{"correction_type": "no_op"},
                     {"correction_type": "switch_algorithm",
                      "new_scheduling_algorithm": "FCFS", "new_params": {}}]:
        d = cg.validate(_preview(proposed))
        assert d["preview_only"] is True
        assert d["applied"] is False
