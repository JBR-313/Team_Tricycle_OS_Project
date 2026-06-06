"""Determinism + invariants for seed-driven workload jitter."""

from tools.workload_jitter import jitter_workload


def _wl():
    return {
        "id": "demo",
        "target_metric": "avg_waiting_time",
        "processes": [
            {"pid": 1, "arrival_time": 0, "priority": 2,
             "label": "short", "cpu_bursts": [2, 2], "actual_bursts": [2, 2],
             "io_bursts": [2]},
            {"pid": 2, "arrival_time": 5, "priority": 3,
             "label": "long", "cpu_bursts": [12], "actual_bursts": [12],
             "io_bursts": []},
        ],
    }


def test_same_seed_is_deterministic():
    assert jitter_workload(_wl(), 7) == jitter_workload(_wl(), 7)


def test_different_seeds_differ():
    a = jitter_workload(_wl(), 1)
    b = jitter_workload(_wl(), 2)
    assert a != b  # vanishingly unlikely to collide across all fields


def test_structure_and_counts_preserved():
    out = jitter_workload(_wl(), 42)
    src = _wl()["processes"]
    op = out["processes"]
    assert len(op) == len(src)
    for s, o in zip(src, op):
        assert o["pid"] == s["pid"]
        assert o["priority"] == s["priority"]
        assert o["label"] == s["label"]
        # per-process burst / io COUNTS are preserved (only magnitudes vary)
        assert len(o["cpu_bursts"]) == len(s["cpu_bursts"])
        assert len(o["actual_bursts"]) == len(s["actual_bursts"])
        assert len(o["io_bursts"]) == len(s["io_bursts"])


def test_actual_and_cpu_bursts_stay_mirrored():
    out = jitter_workload(_wl(), 99)
    for p in out["processes"]:
        assert p["actual_bursts"] == p["cpu_bursts"]


def test_bursts_and_arrivals_are_valid():
    out = jitter_workload(_wl(), 123)
    for p in out["processes"]:
        assert p["arrival_time"] >= 0
        assert all(b >= 1 for b in p["cpu_bursts"])
        assert all(b >= 1 for b in p["io_bursts"])


def test_metadata_preserved_and_marked():
    out = jitter_workload(_wl(), 5)
    assert out["id"] == "demo"
    assert out["target_metric"] == "avg_waiting_time"
    assert out["jittered_from_seed"] == 5


def test_bare_list_workload_supported():
    procs = _wl()["processes"]
    out = jitter_workload(procs, 3)
    assert isinstance(out, list)
    assert len(out) == len(procs)
    assert out == jitter_workload(procs, 3)
