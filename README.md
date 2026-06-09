# LLM Sched Copilot

**An LLM-assisted scheduler for xv6** — course project, *Direction B (LLM for OS)*.
Upstage Solar Pro 3 **advises**, an Algorithm Guard **validates**, and **xv6 under
QEMU executes**.

## Core idea
Traditional xv6 scheduling is fixed and visible only through logs. This project
turns it into a trace-verified, LLM-in-the-loop workflow: from *visible* workload
features the LLM proposes a scheduling algorithm, parameters, and burst hints; the
**Algorithm Guard** validates them; and **xv6 is the sole execution authority** —
the LLM is never on the kernel hot path and never picks the next process. We then
*measured* where an LLM actually helps. As the quantitative decision-maker
(algorithm choice, mid-run switching, numeric burst prediction) it **loses** to
cheap classical methods (shown with negative controls); at the **human interface**
(natural-language intent → config, and trace explanation) it **wins**. Conclusion:
*put the LLM at the OS's human-facing layer, not its decision hot path.*

## Architecture
Three host-side phases wrap the kernel; the Orchestrator
(`scripts/orchestrator.py`) sequences them but is **not** the scheduler. All
module interfaces are JSON / JSONL.
```
Before:   workload → analyzer → LLM advisor → Algorithm Guard
Running:  xv6 (QEMU) → trace → parser → metrics → event detector → correction loop
After:    trace explainer → feedback rules (FAIL-only) → dashboard
```

## Main features
- **Six in-kernel scheduling algorithms** — RR, FCFS, Priority+Aging, MLFQ, SJF, SRTF — plus syscalls, implemented in `xv6-riscv/`.
- **Reproducible xv6 execution** — deterministic QEMU `-icount` + fixed-iteration CPU bursts + tick-aligned start, so metrics reproduce run-to-run.
- **Algorithm Guard** — validates every LLM output (algorithm / metric / params / schema); a rejected output falls back to a safe algorithm.
- **Host-side runtime correction** — on a FAIL/starvation run, re-runs xv6 with a Guard-approved fix and records before/after (never in-kernel, never tick-level).
- **Semantic lane** (`--intent`) — natural-language workload intent → a valid scheduling config; the LLM's measured strength (8/8).
- **Observability** — natural-language trace explanation + a React dashboard.
- **Honest evaluation** — leak-free prompts, negative controls, and CIs in `outputs/*/RESULTS.md`.

## File structure
```
xv6-riscv/              the kernel — execution authority (schedulers, syscalls, schedtest.c)
scripts/orchestrator.py host-side control plane that drives the whole pipeline
tools/                  pipeline modules: analyzer · advisor · intent_advisor · guard · trace_parser · metrics · event_detector · correction_* · trace_explainer
experiments/            evidence tools: determinism probe · burst eval · intent eval · ablations
workloads/              workload definitions (*.json)
dashboard_live/         React observability dashboard
docs/                   design notes + course deliverables (technical_report, development_process, presentation/)
outputs/                generated metrics/traces + RESULTS.md evidence
```

## Pipeline
```bash
cp .env.example .env                                 # add UPSTAGE_API_KEY
python3 scripts/orchestrator.py --workload interactive
#   [1] analyze  [2] advise  [3] guard  [4] run on xv6 (all 6 algorithms)
#   [5] export   [6] validate [7] correct [8] explain [9] feedback (FAIL-only)
python3 scripts/orchestrator.py --intent "Interactive desktop; latency matters."  # NL → config
cd dashboard_live && npm install && npm run dev      # dashboard at http://localhost:5174
cd xv6-riscv && make qemu                            # raw kernel to a shell (Ctrl-A X to quit)
```
Reproduce the evidence:
```bash
python3 experiments/xv6_determinism_probe.py             # runs reproduce run-to-run
python3 experiments/burst_random_eval.py --signal multi  # → outputs/random_eval/RESULTS.md
python3 experiments/intent_eval.py                       # → outputs/intent_eval/RESULTS.md
```
