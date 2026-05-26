# LLM Sched Copilot — Data Format Reference

All module interfaces use JSON or JSON Lines (JSONL).  
All files live under the project root unless noted otherwise.

---

## workloads/*.json

**Format**: JSON array  
**Producer**: Manual (team member)  
**Consumer**: `tools/workload_analyzer.py`

Describes the set of processes that will be scheduled.

```json
[
  {
    "pid": 1,
    "arrival_time": 0,
    "cpu_bursts": [6, 4, 2],
    "io_bursts": [3, 2],
    "priority": 5,
    "label": "cpu_bound"
  },
  {
    "pid": 2,
    "arrival_time": 2,
    "cpu_bursts": [2, 2, 2, 2],
    "io_bursts": [5, 5, 5],
    "priority": 2,
    "label": "interactive"
  },
  {
    "pid": 3,
    "arrival_time": 5,
    "cpu_bursts": [10],
    "io_bursts": [],
    "priority": 7,
    "label": "cpu_bound"
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `pid` | integer | Process ID |
| `arrival_time` | integer | Tick at which the process arrives |
| `cpu_bursts` | integer array | Sequence of CPU burst durations |
| `io_bursts` | integer array | Sequence of I/O burst durations (between CPU bursts) |
| `priority` | integer | Static priority (lower number = higher priority) |
| `label` | string | Human-readable workload type hint (`"cpu_bound"`, `"interactive"`, `"mixed"`) |

**Note**: `cpu_bursts` must not be passed to the LLM as prediction targets.

---

## outputs/workload_summary.json

**Format**: JSON object  
**Producer**: `tools/workload_analyzer.py`  
**Consumer**: `tools/llm_advisor.py` (LLM Workload Interpreter)

Observable summary of the workload. Must not include raw burst sequences.

```json
{
  "process_count": 3,
  "avg_arrival_gap": 2.5,
  "cpu_bound_ratio": 0.67,
  "interactive_ratio": 0.33,
  "avg_priority": 4.7,
  "priority_variance": 3.9,
  "has_starvation_risk": true,
  "burst_count_distribution": {"min": 1, "max": 4, "avg": 2.7},
  "total_cpu_work": 30,
  "workload_file": "workloads/priority_starvation.json"
}
```

---

## outputs/recommendation.json

**Format**: JSON object  
**Producer**: `tools/llm_advisor.py` (LLM Scheduling Algorithm Advisor)  
**Consumer**: `tools/algorithm_guard.py`, dashboard

```json
{
  "recommended_scheduling_algorithm": "MLFQ",
  "params": {
    "queues": 3,
    "quantum": [2, 4, 8],
    "aging_threshold": 30,
    "boost_interval": 100
  },
  "target_metric": "avg_response_time",
  "risks": ["starvation_if_aging_too_weak"],
  "reason": "The workload contains multiple short interactive jobs mixed with long CPU-bound jobs. MLFQ favors short jobs while still allowing CPU-bound jobs to make progress.",
  "workload_interpretation": {
    "workload_type": "interactive_heavy",
    "main_risks": ["poor_response_time", "starvation"]
  },
  "llm_model": "solar-pro3",
  "timestamp": "2026-05-20T10:00:00Z"
}
```

---

## outputs/guard_decision.json

**Format**: JSON object  
**Producer**: `tools/algorithm_guard.py`  
**Consumer**: xv6 / `tools/scheduler_simulator.py`

```json
{
  "guard_result": "accepted",
  "scheduling_algorithm": "MLFQ",
  "params": {
    "queues": 3,
    "quantum": [2, 4, 8],
    "aging_threshold": 30,
    "boost_interval": 100
  },
  "reason": "MLFQ is implemented and all parameters are in valid ranges.",
  "original_recommendation": "MLFQ",
  "fallback_used": false
}
```

Rejected example:

```json
{
  "guard_result": "rejected",
  "scheduling_algorithm": "MLFQ",
  "params": {
    "queues": 3,
    "quantum": [2, 4, 8],
    "aging_threshold": 30,
    "boost_interval": 100
  },
  "reason": "SRTF requires burst prediction, but no predictor output was provided.",
  "original_recommendation": "SRTF",
  "fallback_used": true
}
```

---

## outputs/trace.jsonl

**Format**: JSON Lines (one event per line)  
**Producer**: xv6 kernel / `tools/scheduler_simulator.py`  
**Consumer**: `tools/trace_parser.py`, `tools/trace_explainer.py`, dashboard

See `docs/trace_format.md` for the full event type specification.

```jsonl
{"tick": 0,  "algo": "MLFQ", "event": "ARRIVE",   "pid": 1, "state": "RUNNABLE", "queue": 0, "priority": 5, "burst_hint": null}
{"tick": 0,  "algo": "MLFQ", "event": "DISPATCH",  "pid": 1, "state": "RUNNING",  "queue": 0}
{"tick": 2,  "algo": "MLFQ", "event": "ARRIVE",    "pid": 2, "state": "RUNNABLE", "queue": 0, "priority": 2, "burst_hint": null}
{"tick": 2,  "algo": "MLFQ", "event": "PREEMPT",   "pid": 1, "state": "RUNNABLE", "queue": 0, "reason": "quantum_expired"}
{"tick": 2,  "algo": "MLFQ", "event": "DISPATCH",  "pid": 2, "state": "RUNNING",  "queue": 0}
{"tick": 4,  "algo": "MLFQ", "event": "PREEMPT",   "pid": 2, "state": "RUNNABLE", "queue": 1, "reason": "quantum_expired"}
{"tick": 30, "algo": "MLFQ", "event": "QUEUE_CHANGE", "pid": 1, "state": "RUNNABLE", "from_queue": 0, "to_queue": 1, "reason": "demotion"}
{"tick": 45, "algo": "MLFQ", "event": "CORRECTION_APPLIED", "pid": -1, "state": null, "correction_type": "parameter_update", "new_params": {"aging_threshold": 20}}   // (Future Work — not emitted by today's preview-only pipeline)
{"tick": 60, "algo": "MLFQ", "event": "EXIT",      "pid": 2, "state": "ZOMBIE",   "queue": 1, "turnaround": 58, "waiting": 50, "response": 2}
```

---

## outputs/metrics.json

**Format**: JSON object  
**Producer**: `tools/metrics.py`  
**Consumer**: `tools/trace_explainer.py`, `tools/feedback_generator.py`, dashboard

```json
{
  "scheduling_algorithm": "MLFQ",
  "params": {"queues": 3, "quantum": [2, 4, 8], "aging_threshold": 30, "boost_interval": 100},
  "process_count": 3,
  "completed_count": 3,
  "total_execution_time": 65,
  "avg_response_time": 1.7,
  "avg_turnaround_time": 42.3,
  "avg_waiting_time": 28.6,
  "throughput": 0.046,
  "max_waiting_time": 48,
  "starvation_occurred": false,
  "starvation_pids": [],
  "preemption_count": 12,
  "per_process": [
    {
      "pid": 1,
      "arrival_time": 0,
      "first_run_time": 0,
      "finish_time": 62,
      "response_time": 0,
      "turnaround_time": 62,
      "waiting_time": 44
    },
    {
      "pid": 2,
      "arrival_time": 2,
      "first_run_time": 4,
      "finish_time": 60,
      "response_time": 2,
      "turnaround_time": 58,
      "waiting_time": 50
    }
  ],
  "judgment": "NEAR-SUCCESS",
  "regret_score": 0.12,
  "workload_file": "workloads/interactive_heavy.json"
}
```

---

## outputs/runtime_events.json

**Format**: JSON object  
**Producer**: `tools/event_detector.py`  
**Consumer**: `tools/runtime_correction.py`, dashboard

```json
{
  "detected_at_tick": 45,
  "scheduling_algorithm": "MLFQ",
  "events": [
    {
      "type": "starvation_warning",
      "pid": 3,
      "waiting_since_tick": 10,
      "current_waiting_time": 35,
      "threshold": 30,
      "severity": "high"
    }
  ],
  "summary": "Process 3 has been waiting for 35 ticks without being dispatched. Starvation threshold is 30 ticks.",
  "correction_requested": true
}
```

Possible event types: `"starvation_warning"`, `"poor_response_time"`, `"too_many_preemptions"`, `"cpu_bound_domination"`, `"high_waiting_time"`, `"burst_prediction_failure"`

---

## outputs/correction.json

**Format**: JSON object  
**Producer**: `tools/runtime_correction.py` (via LLM)  
**Consumer**: `tools/algorithm_guard.py` → xv6 / `tools/scheduler_simulator.py`

```json
{
  "correction_type": "parameter_update",
  "current_scheduling_algorithm": "MLFQ",
  "new_params": {
    "quantum": [2, 4, 8],
    "aging_threshold": 20,
    "boost_interval": 80
  },
  "reason": "The previous aging threshold was too high, causing process 3 to wait excessively. Reducing aging_threshold from 30 to 20 should resolve the starvation.",
  "apply_at": "next_scheduling_point",
  "triggered_by_event": "starvation_warning",
  "llm_model": "solar-pro3",
  "timestamp": "2026-05-20T10:02:15Z"
}
```

Possible `correction_type` values: `"parameter_update"`, `"algorithm_change"`, `"aging_threshold_adjustment"`, `"quantum_adjustment"`, `"process_hint_update"`

---

## outputs/trace_explanation.json

**Format**: JSON object  
**Producer**: `tools/trace_explainer.py` (via LLM)  
**Consumer**: dashboard

```json
{
  "scheduling_algorithm": "FCFS",
  "summary": "FCFS performed poorly on this workload due to the convoy effect.",
  "detected_pattern": "convoy_effect",
  "main_reason": "A long CPU-bound process (P1) arrived first and delayed all subsequent short interactive jobs.",
  "evidence": [
    "P1 ran from tick 0 to tick 40.",
    "P2 arrived at tick 5 but first ran at tick 41.",
    "P3 arrived at tick 8 but first ran at tick 41.",
    "Average response time was 36.0, compared to 2.7 for MLFQ on the same workload."
  ],
  "suggestion": "MLFQ or Round Robin would significantly reduce response time for short interactive jobs.",
  "runtime_corrections_applied": 0,
  "llm_model": "solar-pro3",
  "timestamp": "2026-05-20T10:05:00Z"
}
```

---

## outputs/feedback_rules.md

**Format**: Markdown  
**Producer**: `tools/feedback_generator.py` (via LLM, FAIL only)  
**Consumer**: `tools/llm_advisor.py` (injected into next LLM prompt)

```markdown
# Feedback Rules — Generated 2026-05-20

## Rule 1
**Condition**: burst variance is high AND many interactive jobs arrive after a long CPU-bound job  
**Failed case**: LLM selected FCFS, actual best was MLFQ (regret_score = 0.42)  
**Rule**: If burst variance is high and short interactive jobs arrive after a long CPU-bound job, avoid FCFS. Prefer MLFQ or Round Robin.

## Rule 2
**Condition**: process_count > 5 AND cpu_bound_ratio > 0.7 AND has_starvation_risk = true  
**Failed case**: LLM selected Priority without aging, actual best was MLFQ (regret_score = 0.38)  
**Rule**: When starvation risk is high and most processes are CPU-bound, always include aging or use MLFQ instead of plain Priority scheduling.
```

Only generated on FAIL evaluation. Not generated on SUCCESS or NEAR-SUCCESS.
