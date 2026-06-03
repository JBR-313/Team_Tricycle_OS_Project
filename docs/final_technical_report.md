# LLM Sched Copilot — Technical Report

> **LLM suggests. Algorithm Guard checks. xv6 executes. Trace Parser normalizes. Metrics verify. dashboard_live explains.**

*Operating Systems final project — LLM-for-OS scheduling observability lab.*

This report documents the system as it actually exists. It is explicit about
what is **implemented**, what is **dev/fallback**, and what is **future work**.
The recurring invariant, stated up front and never contradicted below:

> The LLM is not the scheduler. The LLM does not choose the next process at every
> timer tick. The LLM does not directly modify xv6 kernel state. xv6 remains the
> execution authority. The LLM recommendation is a hypothesis. Algorithm Guard
> validates the recommendation. Metrics verify whether the recommendation was
> useful. dashboard_live explains the result visually.

---

## 1. Project Summary

LLM Sched Copilot uses a large language model as a **decision-support layer** for
xv6 CPU scheduling. The LLM reads an *observable* workload summary, recommends a
scheduling algorithm and parameters, and explains results in natural language.
The recommendation is validated by an Algorithm Guard, executed by the real xv6
kernel under QEMU, and verified by a Metrics Evaluator that computes a regret
score and a SUCCESS / NEAR-SUCCESS / FAIL judgment. A React dashboard
(`dashboard_live`) visualizes the whole pipeline.

The primary demo path is **xv6 + QEMU**, driven by the host-side Orchestrator. A
Python scheduler simulator exists only as a development/fallback backend and is
never presented as proof of real xv6 execution.

## 2. Motivation

xv6 scheduling behavior is difficult to understand from raw serial-console logs
or kernel source alone, and choosing the right algorithm for a workload normally
requires expert manual trace reading. We wanted to (a) make xv6 scheduling
**observable** end-to-end, and (b) make the algorithm choice **explainable** —
while being rigorous that the kernel, not the LLM, remains in control. The LLM is
therefore framed as an advisor whose hypotheses are checked, executed, and
measured, not as a controller of kernel state.

## 3. System Architecture

Three phases (see `architecture_diagram.md` for the full diagram):

**Before running**
`workloads/*.json` → Workload Analyzer (`tools/workload_analyzer.py`) →
`workload_summary.json` → LLM Advisor (`tools/llm_advisor.py`) →
`recommendation.json` → Algorithm Guard (`tools/algorithm_guard.py`) →
`guard_decision.json`.

**Running**
Algorithm Guard decision → Orchestrator (`scripts/orchestrator.py --backend xv6`)
→ xv6 build + QEMU boot per algorithm → `schedtest <algo> <seed> <profile>` →
raw serial-console logs → Trace Parser (`tools/trace_parser.py`) →
`trace_<algo>.jsonl` → Metrics Evaluator (`tools/metrics.py`) → `metrics.json`.

**After running**
Trace Explainer / dashboard data export → `dashboard_live/public/live-data/` →
`dashboard_live` (React). A backend badge (`XV6 TRACE` / `SIMULATOR FALLBACK` /
`FALLBACK`) makes the data source explicit.

All module-to-module interfaces are JSON or JSON Lines (JSONL).

## 4. Technology Stack

| Layer | Technology |
|---|---|
| Kernel / scheduler | xv6-riscv (RISC-V), C (K&R style), QEMU `qemu-system-riscv64` |
| Host pipeline | Python 3.12 (Orchestrator, Analyzer, Guard, Trace Parser, Metrics) |
| LLM | Upstage **Solar Pro 3** API (`tools/llm_advisor.py`, `tools/solar_client.py`) |
| Primary dashboard | React + Vite (`dashboard_live`, port 5174) |
| UI sandbox / legacy | `dashboard_test` (React, static fixtures); `dashboard/` (Streamlit, legacy) |
| Contract validation | `tools/validate_dashboard_contract.py` (`--strict`, `--snapshots`, `--preview`) |

## 5. OS Concepts Used

- **Process, process state, ready queue** — reconstructed from the trace
  (ARRIVE/DISPATCH/PREEMPT/SLEEP/WAKEUP/EXIT) by the Trace Parser.
- **CPU scheduling & preemption** — RR, Priority, and SRTF preempt on the timer
  tick; FCFS and SJF run until block/exit; MLFQ preempts on queue demotion
  (`xv6-riscv/kernel/trap.c`).
- **System calls** — `setscheduler`, `getscheduler`, `setpriority`,
  `getpriority` (`xv6-riscv/kernel/syscall.c`, `user/user.h`).
- **Starvation & aging** — Priority+Aging promotes long-waiting processes; the
  Metrics Evaluator detects starvation with hardened, conjunctive gates.
- **Burst prediction** — SJF/SRTF schedule on an EMA `predicted_burst` computed
  from *observed* CPU usage; actual future bursts are never used.

## 6. LLM Integration

- **Input (hypothesis source).** The Workload Analyzer produces a summary of
  *observable* features only. It **never** puts `actual_bursts` into the summary;
  this enforces the burst-prediction rule at the input boundary.
- **Recommendation.** The LLM Advisor (Solar Pro 3) returns
  `recommendation.json`: a scheduling algorithm, parameters, a target metric,
  and optional burst *hints* (`predicted_bursts[]`) based only on visible
  features.
- **Validation.** The Algorithm Guard checks the recommended algorithm is
  implemented, parameters are within safe ranges, the JSON schema is correct,
  and any burst hints are clamped. On failure it rejects and falls back to a safe
  algorithm (RR).
- **Explanation.** After execution, the LLM explains the trace and metrics in
  natural language.
- **No control authority.** The LLM never selects the next process and never
  writes kernel state. Its only outputs are `recommendation.json` and (preview)
  `correction.json`, both gated.
- **Offline fallback.** Without an API key, the Orchestrator uses committed
  `outputs/_demo_fixtures/`, stamps `metadata_source=demo_fallback`, and the
  dashboard badge downgrades to `FALLBACK` — no silent guessing.

## 7. xv6 Scheduler Implementation

Six algorithms in `xv6-riscv/kernel/proc.c` and `trap.c`, switchable at runtime
via `setscheduler`:

| Algorithm | Preemption | Notes |
|---|---|---|
| **RR** | timer tick (quantum) | baseline; preserved as comparison reference |
| **FCFS** | none (run to block/exit) | arrival order |
| **Priority + Aging** | timer tick | aging promotes long-waiting processes |
| **MLFQ** | on demotion | multi-level feedback queues |
| **SJF** | none | EMA `predicted_burst` (no future leak) |
| **SRTF** | timer tick | `predicted_burst − cur_burst_run`, floored |

The EMA predictor (`update_burst_prediction`) uses integer exponential averaging
on already-consumed CPU time (`alpha=50`, `initial=10`, `min=1`, `max=100`). The
`schedtest` user program runs a curated profile under a chosen algorithm and
emits `[SCHED]` / `[SCHEDTEST]` trace lines on the serial console.

## 8. Trace Format

Each scheduling event is one JSON object (JSONL). Representative events:
`PROC_DEF` (planned arrival), `ARRIVE`, `DISPATCH`, `PREEMPT`, `SLEEP`,
`WAKEUP`, `EXIT` (with EXIT-reported response/turnaround/waiting when present),
and `STARVATION_WARNING` (authoritative). The Orchestrator windows each run on
`RUN_BEGIN` / `RUN_END` markers; the windowing is intentionally lenient so an
occasional kernel/user `printf` interleave does not lose a run. See
`docs/trace_format.md`.

## 9. Metrics and Evaluation Rule

```
response_time   = first_run_time − arrival_time
turnaround_time = finish_time − arrival_time
waiting_time    = turnaround_time − total_cpu_burst_time
throughput      = completed_process_count / total_execution_time
```

- **Starvation (hardened, `tools/metrics.py`).** A process is flagged only when
  its wait clears the relative gate (> 3× average), the absolute floor
  (≥ 5 ticks), and the makespan-share gate (≥ 50% of makespan), *and* enough
  processes completed for the average to be robust. An explicit
  `STARVATION_WARNING` trace event is authoritative and bypasses the heuristic.
  Regression tests: `tools/test_metrics_starvation.py`.
- **Regret / judgment.** Every algorithm runs on the identical workload; regret
  is the normalized gap between the LLM-selected algorithm and the best one on
  the workload's `target_metric`. **SUCCESS ≤ 0.10, NEAR-SUCCESS ≤ 0.25, else
  FAIL; starvation ⇒ FAIL.** Constants live in `tools/metrics.py`.

## 10. Dashboard Explanation

`dashboard_live` (React + Vite) reads `public/live-data/` and shows: a backend
badge and manifest meta; the workload summary; the LLM recommendation and
Algorithm Guard decision; per-algorithm Gantt / process lanes / trace stack; an
algorithm comparison and metric visualization with the target-metric judgment;
and the natural-language explanation. `dashboard_test` is a static UI sandbox;
the Streamlit `dashboard/` is a legacy fallback. Live mode polls `manifest.json`
periodically (no websocket).

## 11. Limitations

- xv6 traces are short and sparse (5 children per curated profile, ~30–80
  events) — richer comparisons need larger workloads.
- No websocket streaming; the dashboard polls.
- The runtime-correction loop is **not** closed: detection and a preview-only
  proposer exist, but the apply-inside-xv6 step is not wired.
- The EMA predictor runs but its accuracy (MAE) is not yet measured or
  visualized.
- A Solar Pro 3 API key is required for a live recommendation; otherwise the
  offline fixtures + `FALLBACK` badge are used.

## 12. Future Work

- **Closed-loop runtime correction inside xv6** (detect → propose → guard →
  apply → `CORRECTION_APPLIED`). Currently preview-only and **not** the final
  evaluated path.
- **Seed-diverse xv6 workload generation** (kept out of the final demo for
  reproducibility).
- **Full SJF/SRTF predictor quality evaluation** (MAE dashboard).
- **Websocket streaming** for live updates.
- **LLM burst hints on the xv6 backend** (currently simulator-side only).

## 13. Team Role Distribution

> _Placeholder — fill in before submission._

| Member | Primary area | Key contributions |
|---|---|---|
| _[name]_ | xv6 kernel / scheduler | _[RR/FCFS/Priority+Aging/MLFQ/SJF/SRTF, syscalls, schedtest]_ |
| _[name]_ | LLM integration / Guard | _[advisor, Solar client, algorithm guard, workload analyzer]_ |
| _[name]_ | Pipeline / metrics | _[orchestrator, trace parser, metrics evaluator, contract validator]_ |
| _[name]_ | Dashboard / docs | _[dashboard_live, visualizations, report, presentation]_ |

## 14. Development Process

- **Git workflow.** Feature branches → pull request → squash merge to `main`.
  Recent stabilization PRs: live-data refresh with a real xv6 run (#80), metrics
  starvation hardening (#81), documentation honesty pass (#82).
- **CI.** GitHub Actions runs `py_compile`, the strict dashboard-contract
  validator on committed live-data, and both dashboard builds. **CI does not run
  QEMU/xv6**, so a green badge does not replace the local demo check.
- **Local verification gates.** `scripts/final_demo_check.py` (xv6, seed 42,
  interactive) and `scripts/multi_profile_demo_check.py` (4 curated profiles)
  exercise the real backend end-to-end; the contract validator is run in strict
  mode over live-data and snapshots before any release.
- **Honesty discipline.** Documentation is kept in sync with the implementation;
  dev/fallback and future-work items are labeled as such, and dashboard badges
  never misrepresent the data source.
