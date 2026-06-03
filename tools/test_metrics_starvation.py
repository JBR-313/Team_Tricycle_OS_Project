#!/usr/bin/env python3
"""Regression tests for the starvation-detection hardening in metrics.py.

Covers the three behaviours required by the sparse-trace hardening work:

  1. A sparse / short trace does NOT trigger the statistical starvation
     heuristic (sparse-process gate + makespan-fraction gate).
  2. A genuine long-wait trace DOES trigger starvation.
  3. An explicit STARVATION_WARNING trace event DOES trigger starvation and
     is authoritative — the new gates never suppress it.

Runs two ways, no pytest required:
    python3 tools/test_metrics_starvation.py      # standalone runner
    python3 -m pytest tools/test_metrics_starvation.py

Scope is deliberately limited to tools/metrics.py. It touches neither the
xv6 kernel, the dashboard schema, the orchestrator, nor the trace schema.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `import metrics` work both standalone and under pytest, regardless of
# the working directory the runner was launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import metrics  # noqa: E402
from metrics import (  # noqa: E402
    MIN_COMPLETED_FOR_STARVATION,
    STARVATION_MAKESPAN_FRACTION,
    compute_metrics,
    evaluate_starvation,
)


# ---------------------------------------------------------------------------
# Synthetic trace helpers
# ---------------------------------------------------------------------------
def _proc_events(pid, arrival, first_run, finish, waiting):
    """Minimal event sequence for one completed process.

    Uses EXIT-reported `waiting` so the test controls the waiting time
    directly instead of deriving it from DISPATCH/PREEMPT intervals.
    """
    return [
        {"event": "PROC_DEF", "pid": pid, "arrival": arrival},
        {"event": "DISPATCH", "pid": pid, "tick": first_run},
        {"event": "EXIT", "pid": pid, "tick": finish, "waiting": waiting},
    ]


def _completed_proc(pid, *, finish_time, waiting_time, arrival_time=0):
    """A finalized per-process record as evaluate_starvation consumes it."""
    return {
        "pid": pid,
        "arrival_time": arrival_time,
        "first_run_time": arrival_time,
        "finish_time": finish_time,
        "response_time": 0,
        "turnaround_time": waiting_time,
        "waiting_time": waiting_time,
    }


# ---------------------------------------------------------------------------
# Unit-level: each new gate in isolation
# ---------------------------------------------------------------------------
def test_sparse_process_gate_blocks_starvation():
    """Too few completed processes -> heuristic must not call starvation,
    even when a wait clears every magnitude threshold."""
    assert MIN_COMPLETED_FOR_STARVATION >= 2
    # 2 completed procs (< the gate). One waited the entire run.
    per_process = [
        _completed_proc(1, finish_time=100, waiting_time=90),
        _completed_proc(2, finish_time=100, waiting_time=1),
    ]
    cpu_used = {1: 10, 2: 99}
    occurred, pids, _ = evaluate_starvation(
        per_process, cpu_used, avg_waiting_time=1.0, makespan=100
    )
    assert occurred is False, "sparse trace should not trigger starvation"
    assert pids == []


def test_makespan_fraction_gate_blocks_small_outlier():
    """Enough processes and the relative+absolute thresholds are cleared,
    but the wait is a tiny share of the run -> no starvation."""
    # 4 completed procs, avg wait ~1 tick, one small 6-tick outlier on a
    # 100-tick run. 6 > 3*avg and 6 >= 5, but 6 < 0.5*100 -> blocked.
    per_process = [
        _completed_proc(1, finish_time=100, waiting_time=6),
        _completed_proc(2, finish_time=100, waiting_time=1),
        _completed_proc(3, finish_time=100, waiting_time=1),
        _completed_proc(4, finish_time=100, waiting_time=0),
    ]
    cpu_used = {1: 0, 2: 0, 3: 0, 4: 0}
    occurred, pids, threshold = evaluate_starvation(
        per_process, cpu_used, avg_waiting_time=1.0, makespan=100
    )
    assert occurred is False, "small outlier should be blocked by makespan gate"
    assert pids == []
    # Reported threshold is the binding gate: 0.5 * 100 = 50.
    assert threshold == STARVATION_MAKESPAN_FRACTION * 100


def test_genuine_long_wait_triggers_starvation():
    """A process that waits a large share of a long run clears all gates."""
    per_process = [
        _completed_proc(1, finish_time=100, waiting_time=90),
        _completed_proc(2, finish_time=100, waiting_time=1),
        _completed_proc(3, finish_time=100, waiting_time=1),
        _completed_proc(4, finish_time=100, waiting_time=1),
    ]
    cpu_used = {1: 10, 2: 99, 3: 99, 4: 99}
    avg = (90 + 1 + 1 + 1) / 4
    occurred, pids, _ = evaluate_starvation(
        per_process, cpu_used, avg_waiting_time=avg, makespan=100
    )
    assert occurred is True, "genuine long wait should trigger starvation"
    assert pids == [1]


def test_zero_average_is_guarded():
    """Degenerate avg waiting time (all-zero waits) never starves."""
    per_process = [
        _completed_proc(i, finish_time=10, waiting_time=0) for i in range(1, 5)
    ]
    occurred, pids, threshold = evaluate_starvation(
        per_process, {}, avg_waiting_time=0.0, makespan=10
    )
    assert occurred is False
    assert pids == []
    assert threshold is None


# ---------------------------------------------------------------------------
# End-to-end: the three required cases through compute_metrics()
# ---------------------------------------------------------------------------
def test_compute_metrics_sparse_trace_no_starvation():
    """A short, sparse trace must report starvation_occurred=False."""
    events = []
    events += _proc_events(1, arrival=0, first_run=0, finish=30, waiting=20)
    events += _proc_events(2, arrival=0, first_run=1, finish=30, waiting=1)
    m = compute_metrics(events)
    assert m["completed_count"] < MIN_COMPLETED_FOR_STARVATION
    assert m["starvation_occurred"] is False
    assert m["starvation_pids"] == []


def test_compute_metrics_real_long_wait_starvation():
    """A trace where one process waits ~90% of the makespan triggers."""
    events = []
    # makespan spans tick 0..100.
    events += _proc_events(1, arrival=0, first_run=0, finish=100, waiting=90)
    events += _proc_events(2, arrival=0, first_run=1, finish=10, waiting=1)
    events += _proc_events(3, arrival=0, first_run=2, finish=11, waiting=1)
    events += _proc_events(4, arrival=0, first_run=3, finish=12, waiting=1)
    m = compute_metrics(events)
    assert m["completed_count"] >= MIN_COMPLETED_FOR_STARVATION
    assert m["starvation_occurred"] is True
    assert 1 in m["starvation_pids"]


def test_compute_metrics_explicit_warning_is_authoritative():
    """An explicit STARVATION_WARNING triggers starvation even on a sparse
    trace the heuristic would (and does) leave clean — the gates must not
    suppress an authoritative kernel/sim signal."""
    events = []
    events += _proc_events(1, arrival=0, first_run=0, finish=30, waiting=2)
    events += _proc_events(2, arrival=0, first_run=1, finish=30, waiting=1)
    # Sanity: without the warning this sparse trace does not starve.
    baseline = compute_metrics(list(events))
    assert baseline["starvation_occurred"] is False

    events.append({"event": "STARVATION_WARNING", "pid": 2, "tick": 25})
    m = compute_metrics(events)
    assert m["starvation_occurred"] is True
    assert 2 in m["starvation_pids"]


# ---------------------------------------------------------------------------
# Standalone runner (no pytest dependency)
# ---------------------------------------------------------------------------
def _main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL  {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  ERROR {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_main())
