# Technical Report — LLM Sched Copilot

**Direction B — LLM for OS.** An LLM acts as a *hint oracle* for a classical OS
mechanism (CPU scheduling): the LLM proposes a scheduling algorithm, parameters,
and per-process burst hints; an in-kernel/host **Algorithm Guard** decides whether
to follow them; and **xv6 remains the execution authority**. The LLM never picks the
next process and is never on the kernel hot path.

> This report is deliverable #2 (§5). It is the canonical technical overview; the
> design notes under `docs/` (architecture, data_format, trace_format,
> orchestrator_design, system_limitations, evaluation_plan) are the supporting
> detail it references.

---

## 1. One-paragraph summary

A kernel's *fixed* scheduling algorithm and *fixed* parameters are not optimal for
every workload. LLM Sched Copilot tests whether an LLM can close that gap by
recommending, correcting, and explaining xv6 scheduling decisions. The system is a
closed loop: a workload is analysed into visible features, the LLM (Upstage Solar
Pro 3) recommends an algorithm + parameters, an Algorithm Guard validates the
recommendation, xv6 (under QEMU) executes it and emits a scheduling trace, metrics
are computed, a post-evaluation **correction** re-runs the measured-best algorithm
when the recommendation was sub-optimal, and an LLM **trace explainer** narrates the
result. The headline finding is reported honestly in §7: the *system* improves over
a fixed default, the LLM contributes a measurable burst-prediction win and natural-
language explanation, but the LLM's standalone *algorithm selection* is bounded by
an information ceiling — a result we establish by measurement rather than assert.

## 2. System architecture (block diagram)

```text
BEFORE RUNNING
  workloads/*.json
    └─▶ Workload Analyzer (tools/workload_analyzer.py)        ─▶ workload_summary.json   (visible features only)
          └─▶ LLM Advisor (tools/llm_advisor.py, Solar Pro 3) ─▶ recommendation.json     (algo + params + burst hints)
                └─▶ Algorithm Guard (tools/algorithm_guard.py)─▶ guard_decision.json     (validated | rejected→safe fallback)

RUNNING  (xv6 = execution authority)
  guard_decision.json
    └─▶ QEMU + xv6 + user/schedtest.c   ──(kernel [SCHED] events)──▶ raw console log
          └─▶ Trace Parser (tools/trace_parser.py)              ─▶ trace_<algo>.jsonl
                └─▶ Metrics (tools/metrics.py) + Event Detector  ─▶ metrics.json + runtime_events.json
                      └─▶ Correction (tools/correction_proposer.py → Guard → host re-run)
                                                                 ─▶ correction_applied.json

AFTER RUNNING
  trace + metrics
    └─▶ Trace Explainer (tools/trace_explainer.py, Solar Pro 3) ─▶ trace_explanation.json
    └─▶ Feedback Rule Generator (FAIL-only)                      ─▶ feedback_rules.md
    └─▶ GUI Observability Dashboard (dashboard_live/, React)     ─▶ live visualisation

  Host control plane that wires all of the above: scripts/orchestrator.py
```

Fallback path: when QEMU/xv6 is unavailable, `tools/scheduler_simulator.py` runs the
same algorithms as a Python model (clearly badged `SIMULATOR FALLBACK`; never
presented as real xv6 execution).

## 3. Tech stack

| Layer | Technology |
|---|---|
| Kernel / OS | xv6-riscv (RISC-V), QEMU `qemu-system-riscv64`, K&R C |
| Scheduling | RR · FCFS · Priority+Aging · MLFQ · SJF · SRTF (in-kernel, `kernel/proc.c`) |
| Host control plane | Python 3 (`scripts/orchestrator.py`) |
| LLM | Upstage **Solar Pro 3** via OpenAI-compatible API (`tools/solar_client.py`), temperature 0 |
| Interfaces | JSON / JSONL between every module (no CSV) |
| Dashboard | React + Vite (`dashboard_live/`), Vitest |
| Tests | pytest (191) + Vitest (28) |

## 4. OS concepts exercised (and where)

The OS component is designed and implemented by the team (not merely hosting an LLM):

| OS concept | Where it lives |
|---|---|
| **CPU scheduling** | `kernel/proc.c` — six algorithms + aging/boost; `kernel/trap.c` timer-driven preemption |
| **Processes & context switching** | xv6 `proc` table; `user/schedtest.c` forks the workload |
| **System calls** | `setscheduler`/`getscheduler`, `setpriority`/`getpriority`, `setpredictor`, `setrrquantum`, `setmlfqparams`, `setbursthint` (`kernel/sysproc.c`, `kernel/syscall.c`) |
| **Synchronization** | xv6 spinlocks guarding the proc table during scheduling decisions |
| **IPC** | `user/schedtest.c` start-barrier pipe (race-free metadata application before a child runs) |
| **Timer interrupts** | `kernel/trap.c` drives quantum expiry / preemption |

## 5. How the LLM is integrated

- **Input is feature-only and honesty-bounded.** The analyzer exposes *visible*
  features (arrival, priority, I/O count, burst count). Future CPU bursts,
  `total_cpu_work`, and the ground-truth best algorithm are **never** placed in a
  prompt (`tools/llm_advisor.py` strip keys). SJF/SRTF burst *hints* are predictions
  from visible features, refined by the kernel's EMA from observed bursts only.
- **The LLM proposes; the Guard disposes.** Every LLM output (recommendation and any
  runtime-correction proposal) is validated by `tools/algorithm_guard.py`:
  implemented algorithm? parameters in range? JSON schema valid? Rejected output
  falls back to a safe algorithm. This is the "OS decides whether to follow the
  hint" contract from the assignment.
- **Correction is a host-side post-evaluation re-run**, not a mid-run kernel
  injection: when the recommendation is judged FAIL, the measured-best algorithm is
  re-run and a before/after comparison is written to `correction_applied.json`.
- **After-running**, the LLM explains the trace in natural language and (FAIL-only)
  generates feedback rules; feedback *consumption* is opt-in (`--use-feedback`) so
  the default demo stays deterministic.

## 6. Key implementation details

- **Hidden-burst separation** (kernel-parity): execution decrements the real burst;
  SJF/SRTF read only the EMA `predicted_burst`, never the ground truth. Mirrored in
  the simulator (`Predictor`, `_pick_sjf/_pick_srtf`).
- **Race-free metadata application**: `schedtest` applies priority / burst hint to a
  child *before* releasing it through a one-byte pipe barrier, so no quantum runs
  under stale defaults.
- **Algorithm Guard regret judgment**: SUCCESS / NEAR-SUCCESS / FAIL by metric
  regret vs the measured best; starvation forces FAIL (`tools/metrics.py`).
- **Deterministic demo**: Solar at temperature 0; the orchestrator publishes a
  validated dashboard data contract (`tools/validate_dashboard_contract.py`).

## 7. Evaluation & limitations (honest findings)

The premise — *fixed scheduling is not optimal for all workloads* — is confirmed:
no single static algorithm wins on every profile, and the closed-loop **system beats
a fixed stock-RR default** on a majority of measured profiles. The honest limits of
the *LLM's* contribution, established by measurement:

1. **LLM standalone algorithm selection is information-bounded.** On the xv6-measured
   set, a trivial *always-MLFQ* baseline (~0.58) is not beaten by the LLM
   (facts-only ~0.33; facts+retrieval ~0.42). Root cause: the feature that decides
   RR-best vs MLFQ-best is burst/convoy structure — exactly what the no-future-burst
   honesty rule hides. (`outputs/learning/RESULTS.md`)
2. **The safety net works *because* it falls back to measurement.** Correction picks
   the measured-best, so the performance gain over a fixed default is driven by the
   evaluate-and-correct loop, not by LLM "intelligence." This is by design — it
   guarantees the LLM can never degrade execution.
3. **A genuine, narrow LLM win exists in burst prediction.** Zero-shot from visible
   features, the LLM beats a blind EMA cold start and a hand-coded heuristic on
   burst *ordering* (~0.90 vs 0.50 / 0.72), which lowers SRTF average waiting on
   workloads with visible heterogeneity — but it can *hurt* on fully homogeneous
   workloads (over-differentiation). (`outputs/ablation/burst_scheduling_RESULTS.md`)
4. **Mid-run adaptive switching is not a robust win here.** In an idealised simulator
   the headroom over the best static algorithm is marginal (4–9%) and collapses to
   zero once a context-switch cost is modelled; on real xv6 the metric pipeline is
   non-deterministic at the ±1-tick level (wall-clock-spin bursts), which swamps the
   effect. (`outputs/adaptive/RESULTS.md`)

**Conclusion.** The LLM's defensible, irreplaceable value in this setting is **safe
integration + natural-language explanation/observability**, plus a measured
burst-ordering edge — not raw scheduling-performance optimisation. We consider the
rigorous, mechanistic characterisation of *where the LLM helps and where it does
not* to be the project's primary contribution.

## 8. Reproducibility

`python3 scripts/final_demo_check.py` (7 health checks, no API key needed) ·
`python3 scripts/orchestrator.py --backend xv6 --workload cpu_bound` (full live run) ·
`cd dashboard_live && npm run dev` (dashboard). See README §10.3 for setup and the
Solar API key. Tests: `pytest` (191) and `cd dashboard_live && npm test` (28).
