# LLM Sched Copilot — Implementation Status

This document is the honest, single-source status of the project during the
Orchestrator-centric refactor. It records what actually works today, what is
in progress, and what is still future work.

The project is mid-refactor. The target final execution path is:

```
Orchestrator
  -> workload selection
  -> workload_analyzer
  -> llm_advisor
  -> algorithm_guard
  -> QEMU/xv6 boot
  -> xv6 schedtest execution
  -> xv6 scheduler logs
  -> trace_parser
  -> metrics
  -> dashboard_live/public/live-data/
  -> dashboard_live
```

The Python simulator is used for fast UI development and fallback comparison.
The final experiment path is xv6 schedtest driven by the host-side Orchestrator.

---

## Status legend

| Status | Meaning |
|--------|---------|
| Implemented | Works today and is used in the normal flow. |
| In progress | Started but not yet end-to-end; do not rely on it for a demo. |
| Partial / Future Work | Only a fragment exists; the full feature is not wired. |

Note: "Implemented" means the code path exists and runs. It does not claim a
formal test suite has been executed.

---

## Status table

| Feature | Status | Evidence File | Run Command | Remaining Risk |
|---------|--------|---------------|-------------|----------------|
| xv6 RR / FCFS / Priority+Aging / MLFQ | Implemented | `xv6-riscv/kernel/proc.c`, `xv6-riscv/user/schedtest.c` | `cd xv6-riscv && make qemu` then `schedtest rr\|fcfs\|priority\|mlfq` | Kernel trace lines are still sparse; rich `[SCHED]` events per the trace format are not all emitted yet. |
| xv6 SJF / SRTF (burst predictor) | Implemented | `xv6-riscv/kernel/proc.c`, `xv6-riscv/user/schedtest.c` | `cd xv6-riscv && make qemu` then `schedtest sjf\|srtf` | Predictor is exponential-averaging based; actual future bursts must never be leaked. Quality of prediction not yet evaluated against metrics. |
| Orchestrator — simulator backend | Implemented | `scripts/orchestrator.py`, `tools/scheduler_simulator.py` | `python3 scripts/orchestrator.py --backend simulator --seed 42 --workload interactive --run-all` | The simulator is a host-side model, not proof of real xv6 execution. |
| Orchestrator — xv6 backend (QEMU automation + schedtest seed/profile + rich kernel traces) | In progress / not yet end-to-end | `scripts/orchestrator.py` (xv6 path), `xv6-riscv/user/schedtest.c` | `python3 scripts/orchestrator.py --backend xv6 --seed 42 --workload interactive --run-all` | QEMU boot automation, deterministic seed/profile injection into `schedtest`, and full kernel trace emission are not complete. The `--backend {xv6,simulator}` / `--seed` / `--run-all` CLI itself is part of this in-progress work. |
| trace_parser — real xv6 log support | Implemented (recently fixed) | `tools/trace_parser.py` | `python3 tools/trace_parser.py --input <log> --algo MLFQ --out-dir outputs/live --seed 42 --profile interactive` | Depends on the kernel actually emitting `[SCHED]` / `[SCHEDTEST]` lines, which the xv6 backend does not yet fully produce. |
| Python simulator (dev / fallback comparison) | Implemented | `tools/scheduler_simulator.py` | `python3 tools/scheduler_simulator.py --workload workloads/interactive_heavy.json --guard outputs/demo/guard_decision.json --out-dir outputs/live` | Not the final backend. Must not be presented as real xv6 execution. Do not delete — it powers UI development and comparison. |
| Algorithm Guard | Implemented | `tools/algorithm_guard.py` | `python3 tools/algorithm_guard.py` | Currently validates FCFS / RR / Priority / MLFQ; SJF/SRTF guard rules (predictor availability) need expansion. |
| LLM Advisor | Implemented | `tools/llm_advisor.py`, `tools/solar_client.py` | `python3 tools/llm_advisor.py --in workload_summary.json --out recommendation.json` | Requires Solar Pro 3 API key in `.env`. Recommends from FCFS / RR / Priority / MLFQ today. |
| Runtime correction loop (event_detector -> proposer -> LLM -> guard -> apply -> CORRECTION_APPLIED -> dashboard) | Partial / Future Work | `tools/event_detector.py` | `python3 tools/event_detector.py` | Only event detection exists. The proposer, LLM call, guard re-check, apply step, and `CORRECTION_APPLIED` trace event are NOT wired end-to-end. |
| dashboard_live (primary demo) | Implemented | `dashboard_live/`, `dashboard_live/public/live-data/` | `cd dashboard_live && npm install && npm run dev` | Loads generated JSON/JSONL; shows a backend indicator (XV6 TRACE vs SIMULATOR FALLBACK). Real xv6 data depends on the in-progress xv6 backend. |
| dashboard_test (UI lab) | Implemented | `dashboard_test/`, `dashboard_test/src/data/` | `cd dashboard_test && npm install && npm run dev` | Static fixture data only; not real scheduling output by design. |

---

## Summary

- xv6 kernel scheduling (RR, FCFS, Priority+Aging, MLFQ, SJF, SRTF) is implemented.
- The host-side Orchestrator works with the simulator backend.
- The Orchestrator xv6 backend (QEMU automation, seed/profile injection into
  `schedtest`, rich kernel traces) is in progress and not yet end-to-end.
- `trace_parser.py` can parse real xv6 console logs once the kernel emits them.
- The runtime correction loop is only partially built: event detection exists,
  but the close-the-loop steps are future work.
- Both React dashboards run today; the Streamlit dashboard remains as a legacy
  fallback.
