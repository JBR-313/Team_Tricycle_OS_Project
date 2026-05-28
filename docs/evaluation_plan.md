# LLM Sched Copilot — Evaluation Plan

## Purpose

The Metrics Evaluator verifies whether the LLM's Scheduling Algorithm recommendation actually improved scheduling performance.

Every run produces `outputs/metrics.json` containing per-metric values and a final judgment.

---

## Metric Definitions

### Average Response Time

```
response_time(p)    = first_run_time(p) - arrival_time(p)
avg_response_time   = mean of response_time across all completed processes
```

Measures how quickly processes begin receiving CPU time after arrival.  
Particularly important for interactive workloads.

---

### Average Turnaround Time

```
turnaround_time(p)  = finish_time(p) - arrival_time(p)
avg_turnaround_time = mean of turnaround_time across all completed processes
```

Measures the total elapsed time from arrival to completion.

---

### Average Waiting Time

```
waiting_time(p)     = turnaround_time(p) - total_cpu_burst_time(p)
avg_waiting_time    = mean of waiting_time across all completed processes
```

Measures time spent in the ready queue without executing.

---

### Throughput

```
throughput = completed_process_count / total_execution_time
```

Measures how many processes complete per unit of time.  
Higher is better.

---

### Max Waiting Time

```
max_waiting_time = max of waiting_time across all completed processes
```

Identifies the worst-case waiting time.  
A high max_waiting_time with a low average may indicate starvation risk.

---

### Starvation Occurrence

```
starvation_occurred = true  if any process waited more than starvation_threshold ticks
                             without being dispatched
starvation_pids     = list of PIDs that experienced starvation
```

Default `starvation_threshold`: 3× the average waiting time, or a configured absolute tick limit.

A Scheduling Algorithm that causes starvation is penalized in the final judgment regardless of average metrics.

---

### Preemption Count

```
preemption_count = total number of PREEMPT events in trace.jsonl
```

Measures scheduling overhead.  
Excessive preemptions may indicate a time quantum that is too short.  
Zero preemptions for a non-FCFS algorithm may indicate a bug.

---

### Regret Score

```
regret_score = (best_metric - llm_metric) / best_metric
             where metric is avg_response_time (or the target_metric specified in recommendation.json)
```

A value of `0.0` means the LLM matched the best Scheduling Algorithm.  
A value of `1.0` means the LLM result had zero performance relative to the best.

Thresholds (single source of truth: `tools/metrics.py` `SUCCESS_REGRET`, `NEAR_SUCCESS_REGRET`):
- `regret_score <= 0.10` → SUCCESS
- `0.10 < regret_score <= 0.25` → NEAR-SUCCESS
- `regret_score > 0.25` → FAIL

If starvation occurred, the judgment is immediately downgraded to FAIL regardless of regret score.

---

### Burst Prediction Error (Optional)

Only recorded when the Scheduling Algorithm is SJF or SRTF.

```
burst_prediction_error(p, i) = |predicted_burst(p, i) - actual_burst(p, i)|
avg_burst_prediction_error   = mean of burst_prediction_error across all (process, burst) pairs
```

The actual future burst must not be given to the LLM during the Before Running or Running phases.  
Burst prediction error is computed only after execution completes.

---

## Judgment Criteria

| Judgment | Condition |
|----------|-----------|
| **SUCCESS** | `regret_score <= 0.10` AND `starvation_occurred = false` |
| **NEAR-SUCCESS** | `0.10 < regret_score <= 0.25` AND `starvation_occurred = false` |
| **FAIL** | `regret_score > 0.25` OR `starvation_occurred = true` |

The judgment is stored in `outputs/metrics.json` under the `"judgment"` field.

On FAIL, the Feedback Rule Generator is triggered to generate `outputs/feedback_rules.md`.  
On SUCCESS or NEAR-SUCCESS, no feedback is generated.

---

## Comparison Baseline

Every evaluation run must include a Round Robin (RR) baseline run.

The RR baseline uses the default time quantum (no LLM recommendation).

The regret score is computed relative to the best-performing Scheduling Algorithm across all algorithms tested in the same run, not just RR.

---

## Output Summary

All evaluation results are stored in `outputs/metrics.json`.

Key fields:

```json
{
  "scheduling_algorithm": "MLFQ",
  "avg_response_time": 1.7,
  "avg_turnaround_time": 42.3,
  "avg_waiting_time": 28.6,
  "throughput": 0.046,
  "max_waiting_time": 48,
  "starvation_occurred": false,
  "starvation_pids": [],
  "preemption_count": 12,
  "regret_score": 0.12,
  "avg_burst_prediction_error": null,
  "judgment": "NEAR-SUCCESS"
}
```

---

## Evaluation Summary Table

| Metric | Formula | Unit | Good Direction |
|--------|---------|------|----------------|
| avg_response_time | mean(first_run - arrival) | ticks | lower |
| avg_turnaround_time | mean(finish - arrival) | ticks | lower |
| avg_waiting_time | mean(turnaround - cpu_burst) | ticks | lower |
| throughput | completed / total_time | processes/tick | higher |
| max_waiting_time | max(waiting_time) | ticks | lower |
| starvation_occurred | any waiting > threshold | boolean | false |
| preemption_count | count(PREEMPT events) | count | context-dependent |
| regret_score | (best - llm) / best | ratio 0–1 | lower |
| avg_burst_prediction_error | mean(\|predicted - actual\|) | ticks | lower (optional) |

---

## Notes

- `total_cpu_burst_time` is the sum of all CPU burst durations for a process (not including I/O).
- If a process did not complete before the simulation ended, it is excluded from metric calculations and flagged.
- Starvation is evaluated separately from regret score — a low regret score does not override a starvation FAIL.
- The burst prediction error metric is only meaningful for SJF/SRTF runs where a predictor was active.
