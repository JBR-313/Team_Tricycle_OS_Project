# Dashboard Data Contract

All data files live in `dashboard_live/public/live-data/`.
They are produced by `scripts/orchestrator.py` (the old
`scripts/run_live_dashboard_pipeline.py` is a deprecated shim).
All formats are JSON or JSONL (JSON Lines). No CSV.

---

## 1. Trace JSONL (`trace_<algo>.jsonl`)

One JSON object per line, sorted by `tick` ascending.

### Required fields

| Field   | Type     | Values                                                                                  |
|---------|----------|-----------------------------------------------------------------------------------------|
| `tick`  | number   | Simulation clock tick (integer ≥ 0)                                                    |
| `algo`  | string   | `"RR"` \| `"FCFS"` \| `"Priority"` \| `"MLFQ"` \| `"SJF"` \| `"SRTF"`               |
| `event` | string   | `"ARRIVE"` \| `"DISPATCH"` \| `"PREEMPT"` \| `"SLEEP"` \| `"WAKEUP"` \| `"EXIT"` \| `"QUEUE_CHANGE"` \| `"CORRECTION_APPLIED"` |
| `pid`   | number   | Process ID (integer > 0)                                                               |
| `state` | string   | Current process state string                                                           |

### Optional fields

| Field          | Type    | When present                                  |
|----------------|---------|-----------------------------------------------|
| `queue`        | number  | MLFQ queue level (0 = highest priority)       |
| `priority`     | number  | Static priority value                         |
| `reason`       | string  | Why preemption/queue change occurred          |
| `turnaround`   | number  | Filled on EXIT event                          |
| `waiting`      | number  | Filled on EXIT event                          |
| `response`     | number  | Filled on EXIT event                          |
| `from_queue`   | number  | QUEUE_CHANGE source queue                     |
| `to_queue`     | number  | QUEUE_CHANGE destination queue                |
| `burst_hint`   | number  | Predicted remaining burst (SJF/SRTF only)     |

### File name mapping

| Algorithm | File                 |
|-----------|----------------------|
| RR        | `trace_rr.jsonl`     |
| FCFS      | `trace_fcfs.jsonl`   |
| Priority  | `trace_priority.jsonl` |
| MLFQ      | `trace_mlfq.jsonl`   |
| SJF       | `trace_sjf.jsonl`    |
| SRTF      | `trace_srtf.jsonl`   |

### Example

```jsonl
{"tick": 0, "algo": "MLFQ", "event": "ARRIVE", "pid": 1, "state": "RUNNABLE", "queue": 0, "priority": 5, "burst_hint": null}
{"tick": 0, "algo": "MLFQ", "event": "DISPATCH", "pid": 1, "state": "RUNNING", "queue": 0}
{"tick": 2, "algo": "MLFQ", "event": "PREEMPT", "pid": 1, "state": "RUNNABLE", "queue": 0, "reason": "quantum_expired"}
```

---

## 2. `metrics.json`

```json
{
  "scheduling_algorithm": "MLFQ",
  "params": { "queues": 3, "quantum": [2, 4, 8], "aging_threshold": 30, "boost_interval": 100 },
  "process_count": 5,
  "completed_count": 5,
  "total_execution_time": 56,
  "avg_response_time": 1.8,
  "avg_turnaround_time": 24.8,
  "avg_waiting_time": 14.8,
  "throughput": 0.089,
  "max_waiting_time": 38,
  "starvation_occurred": false,
  "starvation_pids": [],
  "preemption_count": 9,
  "per_process": [
    {
      "pid": 1,
      "arrival_time": 0,
      "first_run_time": 0,
      "finish_time": 56,
      "response_time": 0,
      "turnaround_time": 56,
      "waiting_time": 38
    }
  ],
  "comparison": {
    "RR":   { "avg_waiting_time": 20.0, "avg_response_time": 3.2, "avg_turnaround_time": 30.0, "throughput": 0.10, "max_waiting_time": 32, "preemption_count": 10, "starvation_occurred": false, "burst_prediction_error": null, "judgment": "NEAR-SUCCESS" },
    "MLFQ": { "avg_waiting_time": 14.8, "avg_response_time": 1.8, "avg_turnaround_time": 24.8, "throughput": 0.089, "max_waiting_time": 38, "preemption_count": 9, "starvation_occurred": false, "burst_prediction_error": null, "judgment": "SUCCESS" }
  },
  "judgment": "SUCCESS",
  "regret_score": 0.07,
  "workload_file": "workloads/interactive_heavy.json"
}
```

Metric definitions:

| Metric           | Formula                                      |
|------------------|----------------------------------------------|
| response_time    | `first_run_time - arrival_time`              |
| turnaround_time  | `finish_time - arrival_time`                 |
| waiting_time     | `turnaround_time - total_cpu_burst_time`     |
| throughput       | `completed_count / total_execution_time`     |

---

## 3. `recommendation.json`

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
  "reason": "...",
  "workload_interpretation": {
    "workload_type": "interactive_heavy",
    "main_risks": ["poor_response_time", "starvation"]
  },
  "llm_model": "solar-pro3",
  "timestamp": "2026-05-24T00:00:00Z"
}
```

---

## 4. `guard_decision.json`

```json
{
  "guard_result": "accepted",
  "scheduling_algorithm": "MLFQ",
  "params": { "queues": 3, "quantum": [2, 4, 8], "aging_threshold": 30, "boost_interval": 100 },
  "reason": "MLFQ is implemented and all parameters are in valid ranges.",
  "original_recommendation": "MLFQ",
  "fallback_used": false
}
```

`guard_result` values: `"accepted"` | `"rejected"` | `"fallback"`

---

## 5. `workload_summary.json`

```json
{
  "process_count": 5,
  "avg_arrival_gap": 3.0,
  "cpu_bound_ratio": 0.4,
  "interactive_ratio": 0.6,
  "avg_priority": 4.4,
  "priority_variance": 3.8,
  "has_starvation_risk": true,
  "burst_count_distribution": { "min": 1, "max": 4, "avg": 2.4 },
  "total_cpu_work": 48,
  "workload_file": "workloads/interactive_heavy.json",
  "workload_type": "interactive_heavy",
  "target_metric": "avg_response_time",
  "main_risks": ["poor_response_time", "starvation"],
  "reason": "..."
}
```

---

## 6. `manifest.json`

Polled by `dashboard_live` every 1 second in Live Mode.
When `version` or `updated_at` changes, the dashboard reloads all files.

```json
{
  "mode": "simulator",
  "updated_at": "2026-05-24T00:00:00Z",
  "version": 1,
  "workload": "interactive_heavy",
  "algorithms": ["RR", "FCFS", "Priority", "MLFQ", "SJF", "SRTF"],
  "recommended_algorithm": "MLFQ",
  "target_metric": "avg_response_time"
}
```

| Field                  | Type   | Notes                                                 |
|------------------------|--------|-------------------------------------------------------|
| `mode`                 | string | `"simulator"` \| `"xv6-log"` \| `"fallback"`        |
| `updated_at`           | string | ISO 8601 UTC timestamp                                |
| `version`              | number | Incremented on each pipeline run                      |
| `workload`             | string | Workload name (stem of the workload JSON file)        |
| `algorithms`           | array  | Algorithms present in this run's trace files          |
| `recommended_algorithm`| string | LLM-recommended algorithm (after guard validation)    |
| `target_metric`        | string | Optimization target metric key                        |

---

## 7. `trace_explanation.json` (optional)

```json
{
  "scheduling_algorithm": "MLFQ",
  "detected_pattern": "short_job_priority",
  "summary": "...",
  "main_reason": "...",
  "evidence": ["...", "..."],
  "suggestion": "...",
  "runtime_corrections_applied": 0
}
```

---

## Judgment values

| Value        | Meaning                                      |
|--------------|----------------------------------------------|
| `SUCCESS`    | LLM selected the best or near-best algorithm |
| `NEAR-SUCCESS` | LLM result is close to the best result     |
| `FAIL`       | LLM result is clearly worse than the best   |
