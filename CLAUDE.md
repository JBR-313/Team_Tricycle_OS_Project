# CLAUDE.md — LLM Sched Copilot

## Project
LLM Sched Copilot is an LLM-for-OS project.
The LLM acts as a scheduling decision support layer for xv6.
The LLM recommends, corrects, and explains xv6 Scheduling Algorithms.
xv6 executes the Scheduling Algorithm.
The LLM is not the scheduler. xv6 is the execution authority.

## Architecture

### Before Running
Workload Definition → Workload Analyzer → LLM Workload Interpreter → LLM Scheduling Algorithm Advisor → Algorithm Guard

### Running
Algorithm Guard → [xv6 Scheduling Algorithm Execution (final target) | Scheduler Simulator (development fallback)] → Scheduling Trace Collector → Trace Parser → Metrics Evaluator + Event Detector → Runtime Correction Proposer

### After Running
Trace Explainer → Feedback Rule Generator → GUI Observability Dashboard

## Scheduling Algorithms
RR (default, baseline) | FCFS | Priority + Aging | MLFQ | SJF/SRTF (optional, requires burst predictor)

## System Calls
`setscheduler` / `getscheduler` / `setpriority` / `getpriority`

## Run Commands
```bash
make qemu                             # build & run xv6
python3 tools/scheduler_simulator.py  # host-side simulation fallback
streamlit run dashboard/dashboard.py  # GUI Observability Dashboard
```

## LLM Role
- Interprets workload characteristics (before running)
- Recommends Scheduling Algorithm + parameters (before running)
- Proposes runtime corrections when scheduling problems are detected (running)
- Explains Scheduling Trace Logs and Scheduling Metrics in natural language (after running)
- Generates feedback rules when a recommendation fails (after running)

The LLM does NOT control the scheduler directly.
The LLM does NOT choose the next process at every timer tick.
The LLM does NOT directly modify xv6 kernel state.

## Algorithm Guard
Algorithm Guard validates every LLM output before it is applied.
It checks whether the recommended Scheduling Algorithm is implemented, parameters are in valid ranges, and the JSON schema is correct.
Runtime correction proposals are also validated by Algorithm Guard.
Rejected output falls back to a safe Scheduling Algorithm.

## Runtime Correction
Runtime correction is applied from the next scheduling point.
The LLM is not called at every timer tick.
Event Detector watches the Scheduling Trace Log and triggers correction only when a scheduling problem is detected.

## Burst Prediction Rule
Future CPU bursts must not be given to the LLM as input.
SJF/SRTF requires a burst predictor (exponential averaging or LLM-assisted).
Actual future burst values must never be leaked to the LLM.

## Data Interface
All module interfaces use JSON or JSON Lines (JSONL).
Do not use CSV for new interfaces.

```
workloads/*.json          → workload_summary.json → recommendation.json
recommendation.json       → guard_decision.json
guard_decision.json       → trace.jsonl
trace.jsonl               → metrics.json + runtime_events.json
runtime_events.json       → correction.json → guard → next scheduling point
trace.jsonl + metrics.json → trace_explanation.json
metrics.json              → feedback_rules.md (fail only)
```

## Metrics
```
response_time   = first_run_time - arrival_time
turnaround_time = finish_time - arrival_time
waiting_time    = turnaround_time - total_cpu_burst_time
throughput      = completed_process_count / total_execution_time
```

## Recommendation Judgment
```
SUCCESS      = LLM selected the best or near-best Scheduling Algorithm
NEAR-SUCCESS = LLM result is close to the best result
FAIL         = LLM result is clearly worse than the best result
```

## Rules
- API key: `.env` only, never commit. Add `.env` to `.gitignore`.
- xv6 kernel C: follow K&R style, tabs for indent.
- RR baseline must be preserved as comparison reference.
- Do not use the word "policy" — use "Scheduling Algorithm" consistently.
- All module-to-module interfaces must be JSON or JSONL.
- Feedback loop fires only on FAIL evaluation.
