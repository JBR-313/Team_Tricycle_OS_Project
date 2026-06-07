"""Deterministic checks for the burst-prediction ablation metrics/strategies.

The LLM elicitation path needs an API key and is not exercised here; the scoring
math and the baseline strategies are pure functions and fully covered offline.
"""

from burst_ablation import (  # experiments/ on path via conftest
    EMA_INITIAL_DEFAULT,
    HEURISTIC_LONG,
    HEURISTIC_SHORT,
    _actual_first_bursts,
    _mae,
    _pairwise_order_accuracy,
    predict_ema_cold,
    predict_heuristic,
)


def _summary(procs):
    return {"visible_processes": procs}


# --- ground truth ----------------------------------------------------------

def test_actual_first_bursts_prefers_actual_over_cpu_bursts():
    wl = {
        "processes": [
            {"pid": 1, "actual_bursts": [2, 9], "cpu_bursts": [99]},
            {"pid": 2, "cpu_bursts": [12]},        # legacy fallback
            {"pid": 3, "actual_bursts": []},        # no burst -> skipped
        ]
    }
    assert _actual_first_bursts(wl) == {1: 2, 2: 12}


# --- baseline strategies ---------------------------------------------------

def test_ema_cold_is_constant_for_everyone():
    s = _summary([{"pid": 1}, {"pid": 7}])
    assert predict_ema_cold(s) == {1: float(EMA_INITIAL_DEFAULT),
                                   7: float(EMA_INITIAL_DEFAULT)}


def test_heuristic_classifies_short_vs_long_from_features():
    s = _summary([
        {"pid": 1, "io_count": 2, "burst_count": 3},   # IO present -> short
        {"pid": 2, "io_count": 0, "burst_count": 1},   # single burst -> long
        {"pid": 3, "io_count": 0, "burst_count": 4},   # many bursts -> short
    ])
    out = predict_heuristic(s)
    assert out == {1: float(HEURISTIC_SHORT),
                   2: float(HEURISTIC_LONG),
                   3: float(HEURISTIC_SHORT)}


# --- metrics ---------------------------------------------------------------

def test_mae_basic_and_missing_pid_ignored():
    pred = {1: 10.0, 2: 5.0}            # pid 3 missing on purpose
    actual = {1: 12, 2: 2, 3: 100}
    # |10-12| + |5-2| = 2 + 3 = 5 over 2 comparable pids
    assert _mae(pred, actual) == 2.5


def test_mae_none_when_no_overlap():
    assert _mae({9: 1.0}, {1: 1}) is None


def test_pairwise_order_perfect():
    # predicted order matches true order on every pair
    pred = {1: 1.0, 2: 5.0, 3: 9.0}
    actual = {1: 2, 2: 6, 3: 50}
    assert _pairwise_order_accuracy(pred, actual) == 1.0


def test_pairwise_order_reversed_is_zero():
    pred = {1: 9.0, 2: 1.0}
    actual = {1: 1, 2: 9}
    assert _pairwise_order_accuracy(pred, actual) == 0.0


def test_pairwise_order_tie_in_prediction_scores_half():
    pred = {1: 5.0, 2: 5.0}            # tie -> 0.5 credit
    actual = {1: 1, 2: 9}
    assert _pairwise_order_accuracy(pred, actual) == 0.5


def test_pairwise_order_none_when_all_actuals_equal():
    # no true ordering exists -> no comparable pairs
    assert _pairwise_order_accuracy({1: 1.0, 2: 2.0}, {1: 5, 2: 5}) is None
