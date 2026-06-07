# Dashboard Data Contract

All data files live in `dashboard_live/public/live-data/`.
They are produced by `scripts/orchestrator.py`.
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
  "recommended_params": { "queues": 3, "quantum": [2, 4, 8], "aging_threshold": 30, "boost_interval": 100 },
  "applied_params": { "queues": 3, "quantum": [2, 4, 8], "boost_interval": 20, "source": "xv6_fixed_default" },
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

**`params` vs `recommended_params` vs `applied_params` vs
`param_application_status` (xv6 backend honesty).**
`recommended_params` is what the LLM/Guard asked for; `applied_params` is what
the xv6 kernel *actually* used. The xv6 backend applies dynamic parameters for
the **selected** algorithm via syscalls (`setrrquantum`, `setpriorityaging`,
`setmlfqparams`/`setmlfqboost`, `setpredictor`/`setbursthint`) before the
workload runs, so for the selected algorithm `applied_params.source` is
`llm_guard` and carries the values that reached the kernel — RR
(`{quantum, source: llm_guard}`), Priority (`{aging_threshold, priority_source:
schedtest_profile, source: llm_guard}`), MLFQ (`{queues, quantum, boost_interval,
source: llm_guard}`), SJF/SRTF (`{alpha_percent, initial, min, max, burst_hints,
source: llm_guard}`). The Guard validates params only for the **selection**, so
the other algorithms in the comparison sweep run on xv6's compile-time defaults
and report `source: xv6_default`. FCFS has no algorithm-specific parameters
(`{}`). Each `*_PARAMS` trace event proves the value reached and was accepted by
xv6. `param_application_status` classifies the relationship:
`fully_applied` (source `llm_guard`), `fixed_default` (source `xv6_default`), or
`not_applicable` (FCFS). `params` is kept as a legacy mirror of the
recommendation so the existing dashboard keeps working. All fields are additive;
loaders that only read `params` are unaffected. The same per-algorithm
`applied_params` / `recommended_params` / `param_application_status` also appear
on each `comparison` entry.

## 2b. `correction_applied.json` (runtime correction apply loop)

Written by the guarded post-evaluation correction APPLY loop in
`scripts/orchestrator.py` (xv6 backend). When the selected algorithm is judged
`FAIL` (or starves), the loop re-runs xv6 on the **same** mirror workload with a
corrected, Guard-approved algorithm/params, compares before/after, and records:

```json
{
  "applied": true,
  "mode": "post_evaluation_correction",
  "trigger": "fail_judgment",
  "original_algorithm": "MLFQ",
  "corrected_algorithm": "RR",
  "original_params": { "queues": 2, "quantum": [10, 50], "aging_threshold": 100, "boost_interval": 100 },
  "corrected_params": {},
  "corrected_config": "kernel_baseline",
  "original_judgment": "FAIL",
  "corrected_judgment": "SUCCESS",
  "target_metric": "avg_turnaround_time",
  "original_metric_value": 16.75,
  "corrected_metric_value": 8.75,
  "improved": true,
  "reason": "MLFQ judged FAIL on avg_turnaround_time; RR was the best performer — re-run to confirm.",
  "trace_file": "trace_rr_corrected.jsonl"
}
```

`corrected_params` is **empty** with `corrected_config: "kernel_baseline"`: the
correction re-runs the best-performing algorithm with the **same kernel-default
configuration the comparison used** (non-selected comparison runs pass no
dynamic flags). This guarantees the re-run reproduces the value that actually
won — passing tuned "safe defaults" (e.g. RR `quantum=10`) would re-run a
*different* configuration than the xv6 RR baseline (`quantum=1`) that won, and
could never confirm the improvement.

When no correction is warranted (the recommendation met the success criteria, or
the simulator backend is used), the file is `{"applied": false, "reason": ...}`.
This is an **applied** artifact (it may carry `applied=true`), distinct from the
preview-only `correction_proposal.json` / `correction_guard_decision.json`, which
remain `preview_only=true`. The corrected run's trace is published alongside the
six per-algorithm traces under the name in `trace_file`. This is a host-side
closed loop, NOT kernel hot-path LLM control: the LLM never runs in the kernel.

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
| `UNKNOWN`    | Not enough data to judge                      |

### Judgment semantics (canonical)

For a metric, `regret` is computed against the best algorithm in the comparison:

- lower-is-better (`avg_response_time`, `avg_waiting_time`, `avg_turnaround_time`,
  `max_waiting_time`, `preemption_count`): `regret = (value - best) / |best|`
- higher-is-better (`throughput`): `regret = (best - value) / |best|`

Thresholds: `SUCCESS` if `regret <= 0.10`, `NEAR-SUCCESS` if `regret <= 0.25`,
else `FAIL`. **Starvation always forces `FAIL`.** `UNKNOWN` when the value is
missing.

**Table row JUDGE must be metric-aware.** The Algorithm Comparison table's `JUDGE`
column MUST be recomputed for the currently selected metric (the dropdown), not
taken blindly from `comparison[algo].judgment` — that stored value is computed for
the recommendation's `target_metric` and is stale for any other selected metric.
The stored `metrics.judgment` / `comparison[algo].judgment` remain valid as the
overall *recommendation verdict* for `target_metric`.

---

## Backward-compatible input aliases

Producers SHOULD emit the canonical keys above. Readers accept these legacy
aliases (see `tools/schema_compat.py` and `dashboard_*/src/data/schemaCompat.js`):

| Canonical                          | Legacy alias accepted        |
|------------------------------------|------------------------------|
| `recommended_scheduling_algorithm` | `algorithm`                  |
| `scheduling_algorithm` (guard)     | `algorithm`                  |
| `avg_response_time`                | `response_time`              |
| `avg_waiting_time`                 | `waiting_time`               |
| `avg_turnaround_time`              | `turnaround_time`            |
| `starvation_occurred`              | `starvation`                 |
| trace `tick`                       | `time`                       |
| trace `algo`                       | `algorithm`                  |

Algorithm display form is `RR, FCFS, Priority, MLFQ, SJF, SRTF` (note mixed-case
`Priority`). Readers normalize `PRIORITY`/`priority` to `Priority`.

### Additional fields

- `guard_decision.guard_result` may also be `"accepted_with_warning"` — the
  dashboard treats it the same as `"accepted"` (a `warnings` array may accompany it).
- `manifest.metadata_source` (optional): set to `"demo_fallback"` when the
  recommendation/guard metadata came from `outputs/_demo_fixtures/` because the live advisor
  or guard step failed. The dashboard should not present demo metadata as a fresh
  run.
