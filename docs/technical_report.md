# Technical Report — LLM Sched Copilot

**Direction B — LLM for OS.** An LLM acts as a *hint oracle* for a classical OS
mechanism (CPU scheduling): the LLM proposes a scheduling algorithm, parameters,
and per-process burst hints; an **Algorithm Guard** decides whether to follow them;
and **xv6 remains the execution authority**. The LLM never picks the next process
and is never on the kernel hot path.

> This report is deliverable #2. It is the canonical technical overview; the design
> notes under `docs/` (architecture_diagram, trace_format, dashboard_data_contract,
> orchestrator_design, system_limitations, evaluation_plan) are the supporting
> detail it references.

---

## 1. One-paragraph summary

A kernel's *fixed* scheduling algorithm and *fixed* parameters are not optimal for
every workload. LLM Sched Copilot tests whether an LLM can close that gap by
recommending, correcting, and explaining xv6 scheduling decisions. The system is a
closed loop: a workload is analysed into visible features, the LLM (Upstage Solar
Pro 3) recommends an algorithm + parameters, an Algorithm Guard validates it, xv6
(under QEMU) executes it and emits a scheduling trace, metrics are computed, a
host-side post-evaluation **correction** re-runs a Guard-approved fix when the
recommendation was sub-optimal, and an LLM **trace explainer** narrates the result.
The honest, measured finding (Section 7): the LLM **loses** in the quantitative
decision hot path (algorithm choice, mid-run switching, numeric burst prediction —
classical methods win, shown with negative controls) but **wins** at the human
interface (natural-language intent to a valid config, and trace explanation). The
contribution is the mechanistic characterisation of *where the LLM helps and where
it does not*, measured on a real, reproducible kernel.

## 2. System architecture (block diagram)

```text
BEFORE RUNNING
  workloads/*.json
    -> Workload Analyzer (tools/workload_analyzer.py)        -> workload_summary.json   (visible features only)
         -> LLM Advisor (tools/llm_advisor.py, Solar Pro 3)  -> recommendation.json     (algo + params + burst hints)
              -> Algorithm Guard (tools/algorithm_guard.py)  -> guard_decision.json     (validated | rejected->safe fallback)

RUNNING  (xv6 = execution authority, deterministic under QEMU -icount)
  guard_decision.json
    -> QEMU + xv6 + user/schedtest.c   --(kernel [SCHED] events)-->  raw console log
         -> Trace Parser (tools/trace_parser.py)             -> trace_<algo>.jsonl
              -> Metrics (tools/metrics.py) + Event Detector -> metrics.json + runtime_events.json
                   -> Correction (correction_proposer -> Guard -> host re-run) -> correction_applied.json

AFTER RUNNING
  trace + metrics
    -> Trace Explainer (tools/trace_explainer.py, Solar Pro 3) -> trace_explanation.json
    -> Feedback Rule Generator (FAIL-only)                      -> feedback_rules.md
    -> GUI Observability Dashboard (dashboard_live/, React)     -> live visualisation

  Host control plane that wires all of the above: scripts/orchestrator.py
```

xv6 is the **only** execution backend (the earlier Python simulator was removed
once the kernel path was made reproducible — see Section 6). When QEMU/no API key
is unavailable, committed offline fixtures keep the dashboard populated (badged
`FALLBACK`, never presented as a real run).

## 3. Tech stack

| Layer | Technology |
|---|---|
| Kernel / OS | xv6-riscv (RISC-V), QEMU `qemu-system-riscv64` (deterministic `-icount`), K&R C |
| Scheduling | RR / FCFS / Priority+Aging / MLFQ / SJF / SRTF (in-kernel, `kernel/proc.c`) |
| Host control plane | Python 3 (`scripts/orchestrator.py`) |
| LLM | Upstage **Solar Pro 3** via OpenAI-compatible API (`tools/solar_client.py`), temperature 0 |
| Interfaces | JSON / JSONL between every module (no CSV) |
| Dashboard | React + Vite (`dashboard_live/`) |
| Tests | pytest (173) + Vitest |

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
  `total_cpu_work`, the ground-truth best algorithm, and free-text `description`/`id`
  are **never** placed in a prompt (`tools/llm_advisor.py` strip keys). SJF/SRTF
  burst *hints* are predictions from visible features, refined by the kernel's EMA
  from observed bursts only.
- **The LLM proposes; the Guard disposes.** Every LLM output is validated by
  `tools/algorithm_guard.py`: implemented algorithm? parameters in range? JSON schema
  valid? Rejected output falls back to a safe algorithm. This is the "OS decides
  whether to follow the hint" contract from the assignment.
- **Correction is a host-side post-evaluation re-run**, not a mid-run kernel
  injection: on a FAIL judgment a Guard-approved fix is re-run and a before/after
  comparison is written to `correction_applied.json`.
- **Semantic lane** (`tools/intent_advisor.py`, `--intent`): a natural-language
  workload description is mapped to a valid scheduling config — the channel where
  the LLM has no classical substitute.
- **After-running**, the LLM explains the trace in natural language and (FAIL-only)
  generates feedback rules; feedback *consumption* is opt-in (`--use-feedback`).

## 6. Key implementation details

- **Reproducible kernel runs.** Three changes make xv6 metrics deterministic
  run-to-run: QEMU `-icount shift=3,sleep=off` (instruction-counted virtual clock),
  fixed-iteration CPU bursts in `run_burst()` (a burst is work, not wall-clock), and
  snapping the run's `t0` to a tick boundary. Verified by
  `experiments/xv6_determinism_probe.py`. This removed the need for the Python
  simulator, which was deleted so xv6 is the single source of truth.
- **Hidden-burst separation** (no-future-burst rule): execution decrements the real
  burst; SJF/SRTF read only the EMA `predicted_burst`, never the ground truth.
- **Race-free metadata application**: `schedtest` applies priority / burst hint to a
  child *before* releasing it through a one-byte pipe barrier, so no quantum runs
  under stale defaults.
- **Regret judgment**: SUCCESS / NEAR-SUCCESS / FAIL by metric regret vs the measured
  best; starvation forces FAIL (`tools/metrics.py`, `docs/evaluation_plan.md`).
- **Arbitrary-workload injection**: `schedtest --procs "arrival:burst:prio,..."`
  runs generated workloads on the real kernel (used by the random-workload study).

## 7. Evaluation & limitations (honest findings)

The premise — *fixed scheduling is not optimal for all workloads* — is confirmed:
no single static algorithm wins on every profile. The role of the *LLM* was then
measured on the now-reproducible kernel, with negative controls:

1. **Standalone algorithm selection is information-bounded.** A trivial *always-MLFQ*
   baseline is not beaten by the LLM; the deciding feature (burst/convoy structure)
   is exactly what the no-future-burst rule hides. (`outputs/learning/RESULTS.md`)
2. **Burst prediction does not beat conventional methods.** In a leak-free,
   real-kernel A/B over random workloads *with a negative control*, a burst prior
   helps SJF/SRTF only when real signal exists (~+8.5% vs blind EMA); the LLM merely
   ties a trivial heuristic on easy signal and **fails** on a fused two-feature
   signal (ordering 0.505 vs a fair heuristic's 0.736). On the no-signal control no
   strategy wins — the control passes, so the result is not a leak.
   (`outputs/random_eval/RESULTS.md`)
3. **Mid-run adaptive switching is not a robust win here.** The single-switch headroom
   over the best static algorithm is marginal and collapses to zero once a
   context-switch cost is modelled. (`outputs/adaptive/RESULTS.md`)
4. **The LLM wins at the human interface.** Mapping natural-language intent to a
   valid, Guard-approved config scores 8/8 on an OS-textbook rubric, and the LLM
   explains traces in natural language — tasks with no classical substitute.
   (`outputs/intent_eval/RESULTS.md`)
5. **The safety net works because it falls back to measurement.** Correction re-runs
   a Guard-approved fix, guaranteeing the LLM can never degrade execution.

**Conclusion.** The LLM's defensible, irreplaceable value in this setting is at the
**human-facing layer** — natural-language intent to config, and explanation /
observability — not the quantitative decision hot path, where cheap classical
methods win. We consider this rigorous, mechanistic boundary (measured on a real,
deterministic kernel with negative controls) to be the project's primary
contribution.

## 8. Reproducibility

`python3 scripts/final_demo_check.py` (health checks, no API key needed) ·
`python3 scripts/orchestrator.py --workload cpu_bound` (full live run) ·
`python3 experiments/xv6_determinism_probe.py` (reproducibility) ·
`cd dashboard_live && npm run dev` (dashboard). Setup and the Solar API key:
see the root README sections 6–7. Tests: `pytest` (173) and `cd dashboard_live && npm test`.
