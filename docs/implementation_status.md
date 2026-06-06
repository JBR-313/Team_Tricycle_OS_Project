# Implementation Status

Single source of truth for what is implemented, with evidence and limitations.
Honest by design: where something is intentionally *not* built, it says so.

| Feature | Status | Evidence | Limitation |
|---|---|---|---|
| xv6 scheduler — RR (baseline) | Implemented | `xv6-riscv/kernel/proc.c` `sched_rr`; `trap.c` quantum preempt | RR is the default/fallback; dynamic quantum via `setrrquantum` |
| xv6 scheduler — FCFS | Implemented | `proc.c` `sched_fcfs` (two-phase, ctime+pid tie-break) | non-preemptive by design |
| xv6 scheduler — Priority + Aging | Implemented | `proc.c` `sched_priority`; aging via `priority_aging_threshold` | aging counted per scheduler round, not per tick |
| xv6 scheduler — MLFQ | Implemented | `proc.c` `sched_mlfq`; `trap.c` quantum + demotion; boost via `mlfq_cfg.boost_interval` | queues/quanta dynamic (2–5) via `setmlfqparams` |
| xv6 scheduler — SJF / SRTF | Implemented | `proc.c` `sched_sjf` / `sched_srtf`, `predicted_remaining` | depend on burst **prediction**; cold-start makes them resemble FCFS until priors/EMA stabilize |
| Dynamic scheduler params reach kernel | Implemented | syscalls 29–32 + predictor syscalls; `*_PARAMS` trace events | CPUS=1 only (lockless writes safe only on 1 hart) |
| SJF/SRTF burst predictor (EMA) | Implemented | `proc.c` predictor; `cur_burst_run` only | **never** reads true future bursts (`actual_bursts`) — the no-future-burst rule |
| LLM Advisor (Solar Pro 3) | Implemented | `tools/llm_advisor.py` advise mode; `tools/solar_client.py` | needs `UPSTAGE_API_KEY`; strict by default, `--offline-fixture` opt-in |
| Algorithm Guard | Implemented | `tools/algorithm_guard.py` (`guard`, `normalize_params`, compat matrix) | clamps out-of-range params to safe defaults; rejects unimplemented algos to a fallback |
| Orchestrator — simulator backend | Implemented | `scripts/orchestrator.py` `run_simulator_backend` | dev/fallback only; not proof of xv6 |
| Orchestrator — xv6 backend | Implemented | `run_xv6_backend` (build → QEMU → schedtest → parse → metrics) | curated profiles only; QEMU + RISC-V toolchain required |
| Trace Parser | Implemented | `tools/trace_parser.py` `parse_line` / `parse_file`; lenient `RUN_BEGIN` recovery | tolerant of kernel/user printf interleave |
| Metrics Evaluator | Implemented | `tools/metrics.py` `compute_metrics`, `compute_judgment`, `compute_regret` | judgment thresholds: SUCCESS ≤0.10, NEAR ≤0.25 regret; starvation forces FAIL |
| Runtime correction — host-side apply loop | Implemented | `orchestrator.py` `_run_correction_apply_loop`; `correction_applied.json` | post-evaluation re-run only; **no** in-kernel LLM, **no** tick-level control; simulator backend = no-op |
| Trace Explainer | Implemented (step [8]) | `tools/trace_explainer.py`; `run_trace_explainer` | fresh per run or explicit `available:false`; needs API key (else placeholder / demo fixture) |
| Feedback Rule Generator | Implemented (step [9], FAIL-only) | `llm_advisor --mode feedback`; `run_feedback_generator` | GENERATION fires only on FAIL/starvation; never faked without a key; FIFO-capped + deduped at `outputs/live/feedback_rules.md` |
| Feedback consumption (opt-in) | Implemented | `orchestrator.py --use-feedback`; `run_advisor`; `run_server` `use_feedback` | OFF by default → deterministic demo; ON injects `--feedback outputs/live/feedback_rules.md` into advise; manifest `feedback_consumed`/`feedback_rule_count` |
| Dashboard staged flow | Implemented | `dashboard_live/src/App.jsx` DemoPhase machine | IDLE → analyze → reveal → visualize → evaluate |
| Data-source badge | Implemented | `components/SourceBadge.jsx` from manifest | XV6 TRACE / SIMULATOR / FALLBACK / SNAPSHOT / UNKNOWN |
| Fallback modes | Implemented | `data/useRun.js` (xv6 default, explicit fallbacks); `fallbackData.js` (no fake FAIL) | empty fallback shows NO DATA, not a failed run |
| Core unit tests + CI | Implemented | `tests/`, `.github/workflows/ci.yml` pytest step | offline; no API key |
| Live streaming | Not implemented (by design) | — | polling on `manifest.json`; no websocket |
| LLM inside kernel / tick-level correction | Not implemented (by design) | — | xv6 is the execution authority; the LLM never picks the next process |

## Pipeline stage map (`scripts/orchestrator.py`)

```
[1] workload_analyzer  → workload_summary.json
[2] llm_advisor advise → recommendation.json   (strict; --offline-fixture opt-in)
[3] algorithm_guard    → guard_decision.json
[4] backend            → trace_<algo>.jsonl + metrics.json   (simulator | xv6)
[5] export             → dashboard_live/public/live-data + manifest.json
[6] validate contract
[7] correction apply loop (xv6, FAIL/starvation/high-sev) → correction_applied.json
[8] trace_explainer    → trace_explanation.json   (fresh or available:false)
[9] feedback (FAIL-only)→ outputs/live/feedback_rules.md   (GENERATION)
    consumption of these rules in [2] is opt-in: --use-feedback only
```

See also [`system_limitations.md`](system_limitations.md),
[`workload_coverage_matrix.md`](workload_coverage_matrix.md),
[`presentation_defense_notes.md`](presentation_defense_notes.md).
