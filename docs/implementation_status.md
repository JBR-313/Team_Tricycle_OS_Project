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
| Orchestrator — simulator backend | Implemented (dev / fallback) | `scripts/orchestrator.py`, `tools/scheduler_simulator.py` | `python3 scripts/orchestrator.py --backend simulator --seed 42 --workload interactive --run-all` | The simulator is a host-side model, not proof of real xv6 execution. Use it as the fast fallback / dev path. |
| Orchestrator — xv6 backend (QEMU automation + schedtest seed/profile + kernel traces) | Implemented (final demo path) | `scripts/orchestrator.py` (xv6 path), `xv6-riscv/user/schedtest.c` | `python3 scripts/orchestrator.py --backend xv6 --seed 42 --workload interactive --run-all` | The Orchestrator builds the kernel (CPUS=1), boots QEMU per algorithm, types `schedtest <algo> <seed> <profile>`, captures the serial console, windows on RUN_BEGIN/RUN_END, parses to `trace_<algo>.jsonl`, rebases ticks, and aggregates `metrics.json`. Limitations: xv6 traces are short (handful of EXIT events). The starvation rule in `tools/metrics.py` is hardened against this — beyond the relative 3× rule it now also requires an absolute ≥5-tick floor, a minimum completed-process count, and a wait ≥50% of makespan — so trivial waits no longer false-trigger starvation. (Current xv6 `FAIL` judgments on `cpu_bound` / `priority_sensitive` are **regret-driven** — the LLM picked a non-optimal algorithm on a short workload — not starvation.) Kernel/user printf can occasionally interleave (`[SCHEDTEST] event=RUN_BEGIN ...` splits across lines); the windowing is intentionally lenient and matches on bare `RUN_BEGIN`/`RUN_END` substrings. |
| trace_parser — real xv6 log support | Implemented | `tools/trace_parser.py` | `python3 tools/trace_parser.py --input <log> --algo MLFQ --out-dir outputs/live --seed 42 --profile interactive` | Recognizes `[SCHED]`/`[SCHEDTEST]` prefixes only. Lines corrupted by printf interleave (lacking the prefix) are silently skipped — the orchestrator's RUN_BEGIN/RUN_END windowing recovers anyway. |
| Python simulator (dev / fallback comparison) | Implemented | `tools/scheduler_simulator.py` | `python3 tools/scheduler_simulator.py --workload workloads/interactive_heavy.json --guard outputs/_demo_fixtures/guard_decision.json --out-dir outputs/live` | Not the final backend. Must not be presented as real xv6 execution. Do not delete — it powers UI development and comparison. |
| Algorithm Guard | Implemented | `tools/algorithm_guard.py` | `python3 tools/algorithm_guard.py` | Currently validates FCFS / RR / Priority / MLFQ; SJF/SRTF guard rules (predictor availability) need expansion. |
| LLM Advisor | Implemented | `tools/llm_advisor.py`, `tools/solar_client.py` | `python3 tools/llm_advisor.py --in workload_summary.json --out recommendation.json` | Requires Solar Pro 3 API key in `.env`. Recommends from FCFS / RR / Priority / MLFQ today. |
| Runtime correction loop (event_detector -> proposer -> LLM -> guard -> apply -> CORRECTION_APPLIED -> dashboard) | Partial / Future Work | `tools/event_detector.py` | `python3 tools/event_detector.py` | Only event detection exists. The proposer, LLM call, guard re-check, apply step, and `CORRECTION_APPLIED` trace event are NOT wired end-to-end. |
| dashboard_live (primary demo) | Implemented | `dashboard_live/`, `dashboard_live/public/live-data/` | `cd dashboard_live && npm install && npm run dev` | Loads generated JSON/JSONL; shows a backend indicator (XV6 TRACE vs SIMULATOR FALLBACK). Real xv6 data depends on the in-progress xv6 backend. |
| dashboard_test (UI lab) | Implemented | `dashboard_test/`, `dashboard_test/src/data/` | `cd dashboard_test && npm install && npm run dev` | Static fixture data only; not real scheduling output by design. |

---

## Summary

- xv6 kernel scheduling (RR, FCFS, Priority+Aging, MLFQ, SJF, SRTF) is implemented.
- The host-side Orchestrator works end to end with **both** backends:
  - `--backend simulator` — fast dev / fallback path (host-side model).
  - `--backend xv6` — final demo / experiment path (real QEMU + xv6 kernel + `schedtest`).
- `trace_parser.py` parses real xv6 console logs. The orchestrator's RUN_BEGIN /
  RUN_END windowing is intentionally lenient so an occasional kernel/user
  printf interleave does not lose the run.
- Dashboard distinction:
  - `dashboard_live` — primary, loads generated JSON/JSONL from
    `dashboard_live/public/live-data/`. Header shows backend mode
    (`XV6 TRACE` / `SIMULATOR FALLBACK` / `FALLBACK`), manifest version, and
    last updated. A yellow fallback banner appears when no live data exists.
  - `dashboard_test` — static UI lab (fixture data only).
  - `dashboard/` — Streamlit, legacy fallback only.
- The runtime correction loop is only partially built: event detection exists,
  but the close-the-loop steps (proposer → LLM → guard re-check → apply →
  `CORRECTION_APPLIED` trace event) are future work.

## Known limitations (be honest about these in the demo)

- **No websocket streaming.** Live mode polls `manifest.json` periodically;
  there is no push channel.
- **Runtime correction loop is not closed.** `tools/event_detector.py` exists,
  but the rest of the loop is not wired.
- **Solar API key required.** `tools/llm_advisor.py` calls Solar Pro 3 via the
  key in `.env`. Without it, the orchestrator falls back to a baked
  `outputs/_demo_fixtures/recommendation.json` and stamps `metadata_source=demo_fallback`
  in `manifest.json`; the dashboard then downgrades the badge to `FALLBACK`.
- **xv6 traces are short and sparse.** `schedtest` only runs a handful of child
  processes (5 in the curated profiles), so each `trace_<algo>.jsonl` is only
  30–80 events. Simulator traces are typically richer. The starvation rule in
  `tools/metrics.py` is hardened for this regime: a process is only flagged as
  starving when it clears the relative 3× rule **and** an absolute ≥5-tick floor
  **and** a wait ≥50% of makespan, and only when enough processes completed for
  the average to be robust (see `tools/test_metrics_starvation.py`). An explicit
  `STARVATION_WARNING` trace event remains authoritative. As a result a tiny
  waiting-time outlier no longer forces a false `FAIL`; the remaining xv6 `FAIL`
  judgments are regret-driven, not starvation.
- **Kernel/user printf interleave on xv6.** Occasionally a `[SCHEDTEST] event=
  RUN_BEGIN ...` line is split mid-print by a kernel `[SCHED]` line. The
  orchestrator's windowing matches the bare `RUN_BEGIN` / `RUN_END` substrings
  so the data is still recovered.
