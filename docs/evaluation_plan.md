# Evaluation Plan

Every run writes `outputs/metrics.json` with per-metric values and a final
`judgment`. The Metrics Evaluator (`tools/metrics.py`) checks whether the LLM's
recommendation actually scheduled well, relative to the best algorithm in the
same run.

## Metrics (lower is better unless noted)
```
response_time   = first_run_time − arrival_time
turnaround_time = finish_time − arrival_time
waiting_time    = turnaround_time − total_cpu_burst_time
throughput      = completed_process_count / total_execution_time   (higher better)
max_waiting_time = max(waiting_time)        # high vs low avg ⇒ starvation risk
preemption_count = count(PREEMPT events)    # context-dependent
```
- **starvation_occurred**: any process waits > `starvation_threshold` (default 3×
  avg waiting, or a configured absolute) without dispatch. Causes an immediate FAIL.
- **avg_burst_prediction_error** (SJF/SRTF only): `mean(|predicted − actual|)`,
  computed offline. The actual future burst is never given to the LLM.

## Judgment
```
regret_score = (best_metric − llm_metric) / best_metric   # 0 = matched the best
```
relative to the best algorithm across the run on `target_metric`. Thresholds
(single source of truth: `tools/metrics.py` `SUCCESS_REGRET` / `NEAR_SUCCESS_REGRET`):

| judgment | condition |
|---|---|
| **SUCCESS** | `regret ≤ 0.10` AND no starvation |
| **NEAR-SUCCESS** | `0.10 < regret ≤ 0.25` AND no starvation |
| **FAIL** | `regret > 0.25` OR starvation |

Every run includes an RR baseline (default quantum). Regret is vs the best of all
algorithms tested, not just RR.

## Feedback: generation vs consumption
On **FAIL**, the Feedback Rule Generator **generates** rules at
`outputs/live/feedback_rules.md`. **Consumption** (injecting them into a future
advise prompt) is **opt-in only** (`--use-feedback`); the default run consumes
nothing, so results stay deterministic and stale rules can't pollute a
recommendation.
