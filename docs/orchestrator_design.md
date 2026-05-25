# LLM Sched Copilot — Orchestrator Design

## Overview

The Orchestrator is the host-side control plane for LLM Sched Copilot. It drives
one full experiment end to end: it selects a workload, asks the LLM for a
recommendation, validates it with the Algorithm Guard, runs the workload through
a backend (xv6 or the simulator), collects the resulting trace, computes
metrics, and publishes everything to the dashboard.

The Orchestrator is not the scheduler. It does not choose the next process and
it does not perform context switches. xv6 remains the execution authority. The
Orchestrator only coordinates the surrounding modules and the run order.

> **LLM suggests. Algorithm Guard checks. xv6 executes. Metrics verify. GUI explains.**

---

## Why a host-side Orchestrator exists

Before this refactor, the live-data pipeline was a single script
(`run_live_dashboard_pipeline.py`) wired specifically around the simulator. The
xv6 path, the LLM advisor, the guard, and the parser were separate manual steps.
The Orchestrator replaces that with one control plane that owns the whole flow
and records what backend actually produced the data.

It exists because the work that surrounds an experiment cannot live inside xv6:

- `schedtest.c` is a tiny xv6 user program. It runs **inside** the guest under
  QEMU. It cannot open a browser, cannot reach the host filesystem to write
  `dashboard_live/public/live-data/`, and cannot call the Solar Pro 3 LLM API.
  All it can do is set a scheduling algorithm via a system call, fork children,
  and print scheduling lines to the console.
- The LLM call, the Algorithm Guard, the trace parser, the metrics evaluator,
  and the dashboard all live on the host. Something on the host has to sequence
  them, and that is the Orchestrator.

So the division is deliberate: xv6 executes scheduling; the Orchestrator does
everything around execution.

---

## Why the simulator is not the final backend

The Python simulator (`tools/scheduler_simulator.py`) models the scheduling
algorithms on the host. It is fast, deterministic, and convenient, which makes
it ideal for:

- fast UI development for `dashboard_live` and `dashboard_test`,
- generating fixture data,
- a fallback / comparison backend when xv6 is not available.

But it is a model, not the kernel. It is **not proof of real xv6 execution**.
The final experiment path is xv6 `schedtest` driven by the Orchestrator. The
simulator is kept (do not delete it) because development and comparison still
need it, and because it is the safe fallback when the xv6 backend is not ready.

The dashboard makes this distinction visible with a backend indicator:
**XV6 TRACE** when the data came from real xv6 logs, **SIMULATOR FALLBACK** when
it came from the simulator.

---

## Why algorithms run sequentially on the same seed/profile

The whole point of the project is to verify whether the LLM picked a good
scheduling algorithm. That verification is only meaningful if every algorithm is
compared on the **same workload**.

Fair comparison rule:

- The same deterministic workload (the same `seed` + `profile`) is used for
  **every** algorithm.
- Algorithms run **sequentially**, never simultaneously.
- The LLM-selected algorithm runs **first**, then the rest.
- An algorithm is never given a different random workload from the others.

If each algorithm ran with a different random workload, a lower average response
time might just mean it got an easier workload, not that the algorithm is
better. Determinism removes that confound: same arrivals, same bursts, same
priorities, only the scheduling algorithm changes.

Algorithms run sequentially rather than in parallel for two reasons: under QEMU
each run is a separate xv6 boot, and running them one at a time keeps each
trace cleanly attributable to a single algorithm.

### Run-order rule

The LLM-selected algorithm runs first. This makes the demo narrative clear —
"the LLM recommended X; here is X; now here is how X compares to the others on
the exact same workload." The remaining algorithms then run in a fixed order
(RR, FCFS, Priority, MLFQ, SJF, SRTF) for a stable comparison baseline. RR is
always preserved as the comparison reference.

---

## Orchestrator CLI

```bash
python3 scripts/orchestrator.py --backend {xv6,simulator} --seed N --workload PROFILE [--run-all] [--algo NAME]
```

Examples:

```bash
# Simulator backend (works today)
python3 scripts/orchestrator.py --backend simulator --seed 42 --workload interactive --run-all

# xv6 backend (in progress — QEMU automation not yet end-to-end)
python3 scripts/orchestrator.py --backend xv6 --seed 42 --workload interactive --run-all
```

| Flag | Meaning |
|------|---------|
| `--backend {xv6,simulator}` | Execution backend. `xv6` is the final target; `simulator` is the dev/fallback. |
| `--seed N` | Deterministic workload seed. The same seed is used for every algorithm in the run. |
| `--workload PROFILE` | Workload profile name (see mapping below). |
| `--run-all` | Run every algorithm sequentially on the same seed/profile, LLM-selected first. |
| `--algo NAME` | Run a single named algorithm instead of all of them. |

> Status note: the `--backend` / `--seed` / `--run-all` CLI and the xv6 backend
> are part of the in-progress Orchestrator work. The simulator path is the one
> that runs end to end today. See `docs/implementation_status.md`.

### Workload profile mapping

Profiles map to existing files under `workloads/`:

| Profile | Workload file |
|---------|---------------|
| `interactive` | `workloads/interactive_heavy.json` |
| `cpu_bound` | `workloads/long_cpu_bound_first.json` |
| `mixed` | `workloads/mixed_workload.json` |
| `priority_sensitive` | `workloads/priority_sensitive.json` |

---

## manifest.json

The Orchestrator writes `dashboard_live/public/live-data/manifest.json` so the
dashboard knows what produced the current data. It carries the new fields plus
legacy mirrors for backward compatibility with older dashboard code.

New fields:

| Field | Meaning |
|-------|---------|
| `backend` | `"xv6"` or `"simulator"`. |
| `seed` | Deterministic seed used for the run. |
| `workload_type` | Workload profile name. |
| `llm_selected_algorithm` | Algorithm the LLM recommended (runs first). |
| `algorithms_executed` | List of algorithms actually run, in run order. |
| `generated_at` | ISO-8601 UTC timestamp of generation. |
| `orchestrator_version` | Orchestrator schema/version stamp. |

Legacy mirrors (kept for older readers): `mode`, `version`, `workload`,
`algorithms`, `recommended_algorithm`, `target_metric`, `updated_at`.

---

## Data flow

```
                        scripts/orchestrator.py  (host control plane)
                                     │
                 ┌───────────────────┼───────────────────────────────┐
                 │                   │                                │
        workload selection           │                                │
   (profile -> workloads/*.json)     │                                │
                 │                   │                                │
                 ▼                   │                                │
   tools/workload_analyzer.py        │                                │
                 │  workload_summary.json                             │
                 ▼                   │                                │
   tools/llm_advisor.py  (Solar Pro 3)                                │
                 │  recommendation.json                               │
                 ▼                   │                                │
   tools/algorithm_guard.py          │                                │
                 │  guard_decision.json                               │
                 ▼                   │                                │
        backend selection ──────────┘                                │
          │                                                          │
   ┌──────┴───────────────┐                                         │
   │ --backend xv6        │ --backend simulator                     │
   ▼                      ▼                                          │
 QEMU/xv6 boot      tools/scheduler_simulator.py                    │
   │  schedtest run        │  trace_<algo>.jsonl + metrics.json     │
   ▼                       │                                        │
 xv6 scheduler logs        │                                        │
   │  [SCHED]/[SCHEDTEST]   │                                        │
   ▼                       │                                        │
 tools/trace_parser.py     │                                        │
   │  normalized trace_<algo>.jsonl                                 │
   ▼                       ▼                                        │
 tools/metrics.py  ────────┘                                        │
   │  metrics.json                                                  │
   ▼                                                                ▼
 dashboard_live/public/live-data/  (trace_*.jsonl, metrics.json,
   manifest.json, recommendation.json, guard_decision.json,
   workload_summary.json, trace_explanation.json)
   │
   ▼
 dashboard_live  (React; shows XV6 TRACE vs SIMULATOR FALLBACK indicator)
```

For each algorithm in a `--run-all` run, the execution + parse + metrics steps
repeat on the same seed/profile; the LLM-selected algorithm runs first.

---

## Relationship to other docs

- `docs/architecture.md` — three-phase architecture and module responsibilities.
- `docs/trace_format.md` — raw `[SCHED]` / `[SCHEDTEST]` line formats and the
  normalized JSONL fields.
- `docs/implementation_status.md` — honest status of each feature.
- `docs/demo_runbook.md` — how to run the final demo.
