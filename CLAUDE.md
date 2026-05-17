# CLAUDE.md — Visual Scheduler

## Architecture
Workload → LLM Advisor → Algorithm Recommendation → xv6 Scheduler → Trace Collector → Metrics Evaluator → GUI

## Scheduling Algorithms
RR (default) | FCFS | Priority | MLFQ | SJF/SRTF (optional)

## System Calls
`setscheduler` / `getscheduler` / `setpriority` / `getpriority`

## Run Commands
```bash
make qemu                                             # build & run xv6
python3 evaluator/evaluate.py --trace trace.json --algo rr
streamlit run gui/app.py
```

## LLM Role
Analyzes workload → recommends algorithm → explains traces/metrics. Does NOT control scheduler directly.

## Data Format
xv6 trace events (dispatch, preemption, waiting, wakeup, termination) → **JSON** → Python evaluator → GUI

## Metrics
```
response_time   = first_run_time - arrival_time
turnaround_time = finish_time - arrival_time
waiting_time    = turnaround_time - total_cpu_burst_time
throughput      = completed / total_time
```

## Rules
- API key: `.env` only, never commit. Add `.env` to `.gitignore`.
- xv6 kernel C: follow K&R style, tabs for indent.
- RR baseline must be preserved as comparison reference.
