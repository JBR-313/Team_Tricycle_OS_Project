# LLM Sched Copilot — Final Presentation Outline

> **One-line thesis:** *LLM suggests. Algorithm Guard checks. xv6 executes. Trace Parser normalizes. Metrics verify. dashboard_live explains.*

This is the speaker-facing outline for the final Operating Systems presentation.
Slide order: **Problem → Idea → Architecture → OS Concepts → Implementation →
Evaluation → Demo → Limitations → Conclusion.** Each section lists what to put on
the slide and what to say. Keep the honest scope: the LLM is an *advisor*, not the
scheduler; **xv6 is the execution authority**.

The invariant to repeat (say at least twice during the talk):

> The LLM is not the scheduler. The LLM does not choose the next process at every
> timer tick. The LLM does not directly modify xv6 kernel state. xv6 remains the
> execution authority. The LLM recommendation is a hypothesis. Algorithm Guard
> validates the recommendation. Metrics verify whether the recommendation was
> useful. dashboard_live explains the result visually.

---

## 1. Problem (1 slide)

**Slide:** A raw xv6 serial console dump next to a wall of `proc.c` scheduler
source. Caption: *"What is this scheduler actually doing — and is it the right
one for this workload?"*

**Say:**
- xv6 scheduling behavior is hard to understand from raw terminal logs or source
  code alone. You see processes run and exit, but not *why* one algorithm beats
  another on a given workload.
- Choosing a scheduling algorithm (RR vs MLFQ vs SJF…) is a judgement call that
  normally needs an expert and a lot of manual trace reading.
- Goal: make xv6 scheduling **observable** and make the algorithm choice
  **explainable** — without pretending an LLM can replace the kernel.

---

## 2. Idea (1 slide)

**Slide:** The thesis line + a tiny diagram: `LLM (advisor) → Guard → xv6 (authority) → Metrics → Dashboard`.

**Say:**
- Use the LLM **not** as the scheduler, but as a **scheduling decision-support
  layer**: it reads an observable workload summary and *recommends* an algorithm
  + parameters.
- The recommendation is a **hypothesis**. The Algorithm Guard validates it; xv6
  executes it for real; the Metrics Evaluator checks whether the hypothesis
  actually helped (regret score).
- This is an **educational LLM-for-OS observability lab**, not an LLM chatbot.

---

## 3. Architecture (1–2 slides)

**Slide:** the three-phase flow (reuse `architecture_diagram.md`):

```
Workload → Workload Analyzer → LLM Advisor → Algorithm Guard
        → xv6 + QEMU (scripts/orchestrator.py --backend xv6)
        → schedtest execution → raw xv6 scheduler logs
        → Trace Parser → Metrics Evaluator
        → dashboard_live/public/live-data → dashboard_live
```

**Say:**
- **Before running:** Workload Analyzer summarizes *observable* features only
  (no future bursts). LLM Advisor recommends. Algorithm Guard accepts/rejects.
- **Running:** the **host-side Orchestrator** builds the kernel, boots QEMU per
  algorithm, types `schedtest <algo> <seed> <profile>`, captures the serial
  console. Every algorithm runs on the **same deterministic workload** (same
  seed + profile), LLM-selected one first.
- **After running:** Trace Parser normalizes logs → Metrics Evaluator computes
  metrics + judgment → dashboard_live visualizes.
- **Honesty fork:** the Python simulator is a **dev/fallback** backend only and
  is badged `SIMULATOR FALLBACK`; it is never presented as real xv6.

---

## 4. OS Concepts (1–2 slides)

**Slide:** a labeled list mapping each concept to where it shows up.

**Say — connect each concept to the project:**
- **Process / process state / ready queue** — rebuilt by the Trace Parser from
  ARRIVE/DISPATCH/PREEMPT/EXIT events; shown as process lanes in the dashboard.
- **CPU scheduling & preemption** — RR/Priority/SRTF preempt on the timer tick;
  FCFS/SJF run to block/exit; MLFQ preempts on demotion. (Verified in
  `xv6-riscv/kernel/trap.c`.)
- **System calls** — `setscheduler` / `getscheduler` / `setpriority` /
  `getpriority` switch the kernel scheduling mode and priorities.
- **Starvation & aging** — Priority+Aging raises long-waiting processes; the
  Metrics Evaluator detects starvation with hardened gates.
- **Burst prediction** — SJF/SRTF use an EMA predictor on *observed* CPU usage;
  **actual future bursts never reach the scheduler or the LLM.**

---

## 5. Implementation (2 slides)

**Slide A — xv6 kernel (the execution authority):**
- Six algorithms in `xv6-riscv/kernel/proc.c` + `trap.c`:
  **RR** (baseline), **FCFS**, **Priority + Aging**, **MLFQ**, **SJF**, **SRTF**.
- `schedtest` user program runs a curated workload profile under a chosen
  algorithm and emits `[SCHED]` / `[SCHEDTEST]` trace lines.
- EMA burst predictor (`update_burst_prediction`) — integer exponential
  averaging on already-consumed CPU time only.

**Slide B — host-side pipeline (advisor + verification):**
- **LLM Advisor** (`tools/llm_advisor.py`, Solar Pro 3) → `recommendation.json`.
- **Algorithm Guard** (`tools/algorithm_guard.py`) validates algorithm support,
  parameter ranges, JSON schema → accept / reject + safe fallback (RR).
- **Orchestrator** (`scripts/orchestrator.py --backend xv6`) drives QEMU.
- **Trace Parser** (`tools/trace_parser.py`) → per-algorithm `trace_<algo>.jsonl`.
- **Metrics Evaluator** (`tools/metrics.py`) → `metrics.json` + judgment.
- **dashboard_live** (React + Vite) reads `public/live-data/`.

---

## 6. Evaluation (2 slides)

**Slide A — metrics & judgment rule:**
```
response_time   = first_run_time − arrival_time
turnaround_time = finish_time − arrival_time
waiting_time    = turnaround_time − total_cpu_burst_time
throughput      = completed_process_count / total_execution_time
```
- **Starvation:** flagged only when a wait clears the relative (3× avg),
  absolute (≥5 ticks), and makespan-share (≥50%) gates *and* enough processes
  completed; an explicit `STARVATION_WARNING` is authoritative. (Hardened so
  short xv6 traces don't false-FAIL.)
- **Regret / judgment:** normalized regret on the workload's `target_metric` —
  **SUCCESS ≤ 0.10, NEAR-SUCCESS ≤ 0.25, else FAIL; starvation ⇒ FAIL.**

**Slide B — what the numbers showed (curated profiles, xv6 backend, seed 42):**
| Profile | LLM selected | Judgment |
|---|---|---|
| interactive | MLFQ | SUCCESS |
| mixed | MLFQ | SUCCESS |
| cpu_bound | SRTF | FAIL (regret-driven) |
| priority_sensitive | Priority | FAIL (regret-driven) |

**Say:** SUCCESS means the LLM picked the best/near-best algorithm; the FAILs are
*honest* — on short workloads the LLM's pick wasn't optimal, and the regret score
says so. That is the system working as designed: **metrics verify the
hypothesis**, including when it is wrong.

---

## 7. Demo (live — see `docs/demo_runbook.md`)

**Steps:**
1. `python3 scripts/final_demo_check.py` (xv6, seed 42, interactive) — one
   command builds xv6, runs QEMU per algorithm, validates the contract.
2. `cd dashboard_live && npm run dev` → open `http://localhost:5174`.

**Point to (left → right, top → bottom):**
- **Backend badge** — `XV6 TRACE` (real xv6) vs `SIMULATOR FALLBACK` vs
  `FALLBACK` (offline fixtures). The honesty signal.
- **LLM Recommendation + Algorithm Guard** — accepted/rejected, parameters.
- **Gantt / process lanes** — per-algorithm timeline from real xv6 logs.
- **Algorithm Comparison + Metric Visualization** — same workload, every
  algorithm, target-metric judgment.
- **LLM Explanation** — natural-language summary.

---

## 8. Limitations (1 slide — be honest)

**Say plainly:**
- **Sparse xv6 traces** — 5 children per curated profile, ~30–80 events; richer
  comparison would need bigger workloads.
- **No websocket streaming** — the dashboard polls `manifest.json`; no push.
- **Runtime correction is not closed-loop** — `event_detector.py` and a
  preview-only proposer exist, but the apply-inside-xv6 step is **Future Work**.
- **Seed-diverse xv6 workload generation** — kept out of the final demo for
  reproducibility; **Future Work**.
- **Predictor quality (SJF/SRTF MAE)** — the EMA predictor runs, but its
  accuracy is not yet measured/visualized; **Future Work**.

---

## 9. Conclusion (1 slide)

**Slide:** the thesis line again.

**Say:**
- This project is **not** an LLM chatbot and **not** an LLM scheduler. It is an
  **educational LLM-for-OS scheduling observability lab**.
- The LLM proposes a hypothesis; the Algorithm Guard checks it; **xv6 executes
  it as the authority**; metrics verify whether it helped; the dashboard
  explains it.
- We can defend every claim against the running system, and we are explicit
  about what is implemented, what is a dev/fallback, and what is future work.

---

## Appendix — Q&A defense pointers (see `docs/presentation_defense_notes.md`)

- *"Is the LLM picking processes?"* No. The kernel picks at every tick; the LLM
  only chooses the algorithm before the run.
- *"Does SJF cheat by seeing the future?"* No. EMA on observed usage only;
  `actual_bursts` never enters the scheduler or the LLM input (enforced by
  `tools/workload_analyzer.py`).
- *"Is the simulator your result?"* No — it is a dev/fallback model, badged
  `SIMULATOR FALLBACK`. The final result is the xv6 backend.
- *"What if the API key is down?"* The orchestrator uses committed offline
  fixtures and the badge downgrades to `FALLBACK` — no silent guessing.
