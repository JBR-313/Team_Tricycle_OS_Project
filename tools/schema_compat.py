"""
Schema Compatibility — backward-compatible reader layer.

The repo has schema drift between code and committed data files (e.g.
recommendation.json uses either "recommended_scheduling_algorithm" or
"algorithm"; trace events use "tick"/"algo" or "time"/"algorithm"; dashboard
manifests use "backend" or legacy "mode"). These helpers let consumers READ
either spelling without renaming anything globally.

All functions are defensive: a None input is treated as an empty dict and
missing keys never raise.

Run:
    python3 tools/schema_compat.py
"""

from __future__ import annotations

CANONICAL_ALGOS = ["RR", "FCFS", "PRIORITY", "MLFQ", "SJF", "SRTF"]


def normalize_algo(name):
    """Return canonical uppercase algo name.

    'Priority' -> 'PRIORITY', 'mlfq' -> 'MLFQ'. Unknown/None -> the uppercased
    stripped string, or 'RR' if falsy.
    """
    if not name:
        return "RR"
    return str(name).strip().upper()


def get_recommended_algorithm(rec, default="RR"):
    """Return normalized algo from a recommendation.json dict.

    Reads rec['recommended_scheduling_algorithm'] or rec['algorithm'], else
    falls back to default.
    """
    rec = rec or {}
    name = rec.get("recommended_scheduling_algorithm") or rec.get("algorithm")
    return normalize_algo(name) if name else normalize_algo(default)


def get_guard_algorithm(guard, default="RR"):
    """Return normalized algo from a guard_decision.json dict.

    Reads guard['scheduling_algorithm'] or guard['algorithm'], else falls back
    to default.
    """
    guard = guard or {}
    name = guard.get("scheduling_algorithm") or guard.get("algorithm")
    return normalize_algo(name) if name else normalize_algo(default)


def get_event_tick(ev):
    """Return the tick of a trace event dict.

    Prefers ev['tick'] (if present and not None), else ev['time'], else None.
    """
    ev = ev or {}
    tick = ev.get("tick")
    if tick is not None:
        return tick
    return ev.get("time")


def get_event_algo(ev):
    """Return normalized algo from ev['algo'] or ev['algorithm'], else None."""
    ev = ev or {}
    name = ev.get("algo") or ev.get("algorithm")
    return normalize_algo(name) if name else None


def get_backend(manifest):
    """Return 'xv6' or 'simulator' for a dashboard manifest dict.

    If manifest['backend'] is present, use it (normalized to lowercase). Else
    map legacy manifest['mode']: 'xv6-log' -> 'xv6', 'simulator' -> 'simulator',
    anything else -> 'simulator'.
    """
    manifest = manifest or {}
    backend = manifest.get("backend")
    if backend:
        return str(backend).strip().lower()
    mode = manifest.get("mode")
    return "xv6" if mode == "xv6-log" else "simulator"


if __name__ == "__main__":
    sample_rec_new   = {"recommended_scheduling_algorithm": "Priority"}
    sample_rec_old   = {"algorithm": "mlfq"}
    sample_guard_new = {"scheduling_algorithm": "srtf"}
    sample_guard_old = {"algorithm": "fcfs"}
    sample_ev_new    = {"tick": 12, "algo": "rr"}
    sample_ev_old    = {"time": 7, "algorithm": "SJF"}
    sample_mf_new    = {"backend": "XV6"}
    sample_mf_old    = {"mode": "xv6-log"}
    sample_mf_legacy = {"mode": "simulator"}

    print("CANONICAL_ALGOS:", CANONICAL_ALGOS)
    print("normalize_algo('Priority'):", normalize_algo("Priority"))
    print("normalize_algo('mlfq'):", normalize_algo("mlfq"))
    print("normalize_algo(None):", normalize_algo(None))
    print("get_recommended_algorithm(new):", get_recommended_algorithm(sample_rec_new))
    print("get_recommended_algorithm(old):", get_recommended_algorithm(sample_rec_old))
    print("get_recommended_algorithm(None):", get_recommended_algorithm(None))
    print("get_guard_algorithm(new):", get_guard_algorithm(sample_guard_new))
    print("get_guard_algorithm(old):", get_guard_algorithm(sample_guard_old))
    print("get_event_tick(new):", get_event_tick(sample_ev_new))
    print("get_event_tick(old):", get_event_tick(sample_ev_old))
    print("get_event_tick(None):", get_event_tick(None))
    print("get_event_algo(new):", get_event_algo(sample_ev_new))
    print("get_event_algo(old):", get_event_algo(sample_ev_old))
    print("get_event_algo({}):", get_event_algo({}))
    print("get_backend(new):", get_backend(sample_mf_new))
    print("get_backend(old mode):", get_backend(sample_mf_old))
    print("get_backend(legacy mode):", get_backend(sample_mf_legacy))
    print("get_backend(None):", get_backend(None))
