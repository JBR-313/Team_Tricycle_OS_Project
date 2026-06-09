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
Algorithm Guard → xv6 Scheduling Algorithm Execution (the sole execution authority, under QEMU) → Scheduling Trace Collector → Trace Parser → Metrics Evaluator + Event Detector → Runtime Correction Proposer

> The Python scheduler simulator was removed once the xv6 path was made
> reproducible (deterministic QEMU `-icount shift=3,sleep=off` + fixed-iteration
> `run_burst` + tick-aligned start; see `docs/GOAL.md`). xv6 is now the only
> backend; there is no simulator fallback.

### After Running
Trace Explainer → Feedback Rule Generator → GUI Observability Dashboard

## Scheduling Algorithms
RR (default, baseline) | FCFS | Priority + Aging | MLFQ | SJF/SRTF (optional, requires burst predictor)

## System Calls
`setscheduler` / `getscheduler` / `setpriority` / `getpriority`

## Run Commands
```bash
make qemu                             # build & run xv6 (deterministic -icount clock)
python3 scripts/orchestrator.py       # full pipeline (xv6 is the only backend)
cd dashboard_live && npm run dev      # GUI Observability Dashboard
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
Runtime correction is applied as a host-side post-evaluation re-run: a second, ordinary xv6 run with the corrected Guard-approved algorithm/params, then a before/after comparison written to `correction_applied.json`. The LLM never runs in the kernel hot path and the correction is NOT injected mid-run "from the next scheduling point" inside the kernel.
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
runtime_events.json       → correction.json → guard → host-side re-run → correction_applied.json
trace.jsonl + metrics.json → trace_explanation.json
metrics.json              → outputs/live/feedback_rules.md (fail only; GENERATION)
feedback_rules.md         → advise prompt (CONSUMPTION; opt-in via --use-feedback)
workload_summary.json + metrics.json → outputs/learning/outcome_store.jsonl (every run; ACCUMULATION)
outcome_store.jsonl       → advise prompt (CONSUMPTION; opt-in via --use-retrieval)
```

## Feedback Loop (generation vs consumption)
Feedback **generation** is automatic and FAIL-only: a FAIL/starvation run writes
`outputs/live/feedback_rules.md` (the one canonical path). Feedback **consumption**
— injecting those rules back into a future advise prompt — is **opt-in only** via
`scripts/orchestrator.py --use-feedback` (or `use_feedback:true` to run_server).
The default final demo consumes nothing, so it stays deterministic and stale or
overfit rules cannot pollute a recommendation. Feedback never changes the
already-finished run; it only influences FUTURE recommendations when opted in.

## Retrieval Learning Loop (accumulation vs consumption)
The personalization / warm-start layer: the LLM learns a user's RECURRING
workload patterns from accumulated MEASURED outcomes, instead of reasoning blind
from textbook priors each time. **Accumulation** is automatic on every evaluated
run: step `[8b]` appends one `(prompt-safe visible features → measured_best)`
record to `outputs/learning/outcome_store.jsonl` (a stable cross-run path of its
own — NOT the per-run out_dir, NOT the dashboard publish dir). **Consumption** —
injecting the k most similar past outcomes into a future advise prompt — is
**opt-in only** via `scripts/orchestrator.py --use-retrieval` (passes
`--retrieval-store` to `tools/llm_advisor.py`). The default final demo retrieves
nothing, so it stays deterministic. Honesty mirrors the feedback loop: stored
features are visible aggregates only (no per-process bursts, no total_cpu_work),
retrieval is leave-one-out by id (a workload never sees its own answer), and no
future burst durations are ever stored or injected. Measured effect and the
no-drift-correction finding: `outputs/learning_curve/FINDINGS.md`.

This is NOT "the LLM is a better scheduler" — it is the LLM at the human
interface, out of the kernel hot path, learning which Scheduling Algorithm a
recurring workload signature wants. Drift (a change in the user's pattern) is NOT
handled by an explicit runtime correction here: retrieval self-heals within one
instance of the new pattern (measured), so no drift mechanism is added.

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
- Outcome accumulation is automatic every run; retrieval consumption is opt-in via `--use-retrieval` (default OFF keeps the demo deterministic).
