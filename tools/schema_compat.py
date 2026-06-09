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

# Map canonical UPPERCASE algo -> dashboard DISPLAY form (note mixed-case
# "Priority"). Used at OUTPUT boundaries (manifest, comparison keys,
# recommendation/guard output values, trace algo labels).
ALGO_DISPLAY = {
    "RR": "RR",
    "FCFS": "FCFS",
    "PRIORITY": "Priority",
    "MLFQ": "MLFQ",
    "SJF": "SJF",
    "SRTF": "SRTF",
}

# Canonical metric keys used everywhere at output boundaries.
_LOWER_BETTER_METRICS = {
    "avg_response_time",
    "avg_waiting_time",
    "avg_turnaround_time",
    "max_waiting_time",
    "preemption_count",
}
_HIGHER_BETTER_METRICS = {"throughput"}

# Aliases -> canonical metric key.
_METRIC_ALIASES = {
    "response_time": "avg_response_time",
    "waiting_time": "avg_waiting_time",
    "turnaround_time": "avg_turnaround_time",
    "response": "avg_response_time",
    "waiting": "avg_waiting_time",
    "turnaround": "avg_turnaround_time",
    "starvation": "starvation_occurred",
    "avg_starvation": "starvation_occurred",
    # passthrough canonical keys
    "avg_response_time": "avg_response_time",
    "avg_waiting_time": "avg_waiting_time",
    "avg_turnaround_time": "avg_turnaround_time",
    "max_waiting_time": "max_waiting_time",
    "preemption_count": "preemption_count",
    "throughput": "throughput",
    "fairness": "fairness",
    "starvation_occurred": "starvation_occurred",
}


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
    """Return the backend a dashboard manifest claims: 'xv6', 'fallback',
    'simulator' (legacy snapshots only), or 'unknown'.

    The simulator backend was removed: only data that EXPLICITLY claims
    "simulator" is reported as such; an empty/unknown manifest reads as
    'unknown' — it must never default to a backend that no longer exists.
    """
    manifest = manifest or {}
    backend = manifest.get("backend")
    if backend:
        return str(backend).strip().lower()
    mode = str(manifest.get("mode") or "").strip().lower()
    if mode in ("xv6-log", "xv6"):
        return "xv6"
    if mode in ("fallback", "simulator"):
        return mode
    return "unknown"


# ── DISPLAY-form helpers (output boundaries) ────────────────────────────────

def normalize_algorithm_name(value):
    """Return the dashboard DISPLAY form of an algorithm name.

    'priority' -> 'Priority', 'MLFQ' -> 'MLFQ', 'rr' -> 'RR'. Falsy -> 'RR'.
    Unknown names are returned title-cased best-effort (never crashes).
    """
    if not value:
        return "RR"
    canon = str(value).strip().upper()
    if canon in ALGO_DISPLAY:
        return ALGO_DISPLAY[canon]
    # Unknown: keep the original spelling rather than mangling it.
    return str(value).strip()


def normalize_target_metric(value):
    """Return the canonical metric key for a target_metric value.

    response_time -> avg_response_time, waiting_time -> avg_waiting_time,
    turnaround_time -> avg_turnaround_time, starvation -> starvation_occurred,
    throughput/fairness passthrough, avg_*/max_waiting_time/preemption_count
    passthrough. Falsy -> 'avg_response_time'.
    """
    if not value:
        return "avg_response_time"
    key = str(value).strip().lower()
    return _METRIC_ALIASES.get(key, key)


def is_higher_better_metric(metric):
    """True if higher is better for this metric (throughput)."""
    return normalize_target_metric(metric) in _HIGHER_BETTER_METRICS


def is_lower_better_metric(metric):
    """True if lower is better (avg_*/max_waiting_time/preemption_count)."""
    return normalize_target_metric(metric) in _LOWER_BETTER_METRICS


def normalize_recommendation(rec):
    """Return a NEW dict that always has both 'recommended_scheduling_algorithm'
    (DISPLAY form) and legacy 'algorithm', with 'target_metric' normalized to
    canonical. Never crashes on missing fields.
    """
    rec = dict(rec or {})
    name = rec.get("recommended_scheduling_algorithm") or rec.get("algorithm")
    display = normalize_algorithm_name(name)
    rec["recommended_scheduling_algorithm"] = display
    # Keep legacy 'algorithm' (display form keeps both consistent).
    rec.setdefault("algorithm", display)
    if "target_metric" in rec and rec.get("target_metric"):
        rec["target_metric"] = normalize_target_metric(rec.get("target_metric"))
    return rec


def normalize_guard_decision(guard, rec=None):
    """Return a NEW dict that always has 'scheduling_algorithm' (DISPLAY form),
    keeps legacy 'algorithm', and fills 'original_recommendation' /
    'fallback_used' / canonical 'target_metric'. Never crashes.
    """
    guard = dict(guard or {})
    rec = rec or {}

    result = str(guard.get("guard_result", "")).strip().lower()
    fallback_algo = guard.get("fallback_algorithm")
    rejected = result in {"rejected", "fallback"}

    # Effective scheduling algorithm: the fallback when the recommendation was
    # rejected, otherwise the accepted algorithm. Legacy 'algorithm' (which holds
    # the ORIGINAL rejected algo) is preserved untouched.
    if rejected and fallback_algo:
        chosen = guard.get("scheduling_algorithm") or fallback_algo
    else:
        chosen = (
            guard.get("scheduling_algorithm")
            or guard.get("algorithm")
            or rec.get("recommended_scheduling_algorithm")
            or rec.get("algorithm")
            or fallback_algo
        )
    guard["scheduling_algorithm"] = normalize_algorithm_name(chosen)
    guard.setdefault("algorithm", normalize_algorithm_name(chosen))

    if not guard.get("original_recommendation"):
        orig = (
            rec.get("recommended_scheduling_algorithm")
            or rec.get("algorithm")
            or guard.get("algorithm")
        )
        if orig:
            guard["original_recommendation"] = normalize_algorithm_name(orig)

    if "fallback_used" not in guard:
        guard["fallback_used"] = bool(rejected)

    if guard.get("target_metric"):
        guard["target_metric"] = normalize_target_metric(guard.get("target_metric"))
    return guard


def normalize_trace_event(event, default_algo=None):
    """Return a NEW trace-event dict with 'tick' (from tick|time) and 'algo'
    (DISPLAY form from algo|algorithm|default_algo). Never crashes.
    """
    event = dict(event or {})
    tick = event.get("tick")
    if tick is None:
        tick = event.get("time")
    event["tick"] = tick
    algo = event.get("algo") or event.get("algorithm") or default_algo
    if algo:
        event["algo"] = normalize_algorithm_name(algo)
    return event


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

    print("--- DISPLAY-form helpers ---")
    print("ALGO_DISPLAY:", ALGO_DISPLAY)
    print("normalize_algorithm_name('priority'):", normalize_algorithm_name("priority"))
    print("normalize_algorithm_name('MLFQ'):", normalize_algorithm_name("MLFQ"))
    print("normalize_algorithm_name(None):", normalize_algorithm_name(None))
    print("normalize_target_metric('response_time'):", normalize_target_metric("response_time"))
    print("normalize_target_metric('starvation'):", normalize_target_metric("starvation"))
    print("normalize_target_metric(None):", normalize_target_metric(None))
    print("is_higher_better_metric('throughput'):", is_higher_better_metric("throughput"))
    print("is_lower_better_metric('waiting_time'):", is_lower_better_metric("waiting_time"))
    print("normalize_recommendation({'algorithm':'mlfq','target_metric':'response_time'}):",
          normalize_recommendation({"algorithm": "mlfq", "target_metric": "response_time"}))
    print("normalize_recommendation(None):", normalize_recommendation(None))
    print("normalize_guard_decision(rejected):",
          normalize_guard_decision({"guard_result": "rejected", "fallback_algorithm": "rr"},
                                   {"algorithm": "priority"}))
    print("normalize_guard_decision(None):", normalize_guard_decision(None))
    print("normalize_trace_event(old):", normalize_trace_event({"time": 7, "algorithm": "sjf"}))
    print("normalize_trace_event(None, 'mlfq'):", normalize_trace_event(None, "mlfq"))
