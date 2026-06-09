# Workload Coverage Matrix

This catalogs every workload under `workloads/` and classifies how it can be
executed. It exists so the scheduling lab has enough workloads to demonstrate
the differences between algorithms, and so it is always clear **which workloads
run on the real xv6 kernel and which are simulator-only**.

## Backends

- **xv6-backed** — a curated `schedtest.c` profile mirror exists, so the
  workload runs on the real xv6 kernel under QEMU. xv6 has no JSON parser; these
  map to the fixed `schedtest.c` WORKLOADS tables via `XV6_MIRROR_MAP` in
  `scripts/orchestrator.py`. (Arbitrary workloads can be injected at runtime with
  `schedtest --procs "arrival:burst:prio,..."`.)
- **analysis-only** — has a workload JSON but no `schedtest.c` mirror, so the
  orchestrator collapses it to the `mixed` profile when executing on xv6; the JSON
  is still used by the analyzer and the `experiments/` tools.

## Matrix

| Workload (id) | Backend | Target metric | Phenomenon demonstrated |
|---|---|---|---|
| `interactive_heavy` | xv6-backed (`interactive`) | avg_response_time | interactive responsiveness |
| `long_cpu_bound_first` | xv6-backed (`cpu_bound`) | avg_waiting_time | long-job-first head-of-line |
| `mixed_workload` | xv6-backed (`mixed`) | avg_response_time | mixed CPU + interactive |
| `priority_sensitive` | xv6-backed (`priority_sensitive`) | max_waiting_time | priority + aging |
| `short_jobs` | simulator-only | avg_waiting_time | SJF setup (clustered shorts) |
| `starvation_risk` | simulator-only | max_waiting_time | starvation under strict priority |
| `cpu_bound_vs_io_bound` | simulator-only | avg_turnaround_time | CPU vs I/O interleave |
| `ambiguous_mixed` | simulator-only | avg_response_time | ambiguous recommendation case |
| `pure_batch` | simulator-only | avg_turnaround_time | batch throughput (FCFS-friendly) |
| `bursty_long_tail` | simulator-only | avg_waiting_time | long-tail burst distribution |
| `convoy_effect` | simulator-only | avg_waiting_time | **FCFS convoy** — one long job blocks shorts |
| `fairness_rr` | simulator-only | avg_response_time | **RR fair time-slicing** over equal jobs |
| `staggered_short_arrival` | simulator-only | avg_response_time | short jobs trickle in (RR/SRTF favour) |
| `starvation_priority` | simulator-only | max_waiting_time | low-priority starvation vs aging/boost |
| `burst_prediction_demo` | simulator-only | avg_waiting_time | bimodal bursts for the EMA predictor |

## Observed differentiation (generic guard, simulator)

Measured with a generic RR guard (no per-workload tuned params, EMA predictor
cold-start). Differences widen further when the orchestrator runs the LLM
advisor, which supplies the recommended algorithm **and** tuned params/burst
priors for that workload.

| Workload | Strong separation? | Notes |
|---|---|---|
| `convoy_effect` | **yes** | MLFQ ≈ 5.8 vs FCFS ≈ 20.5 avg waiting — clear convoy bust. |
| `fairness_rr` | **yes** | RR 7.5 vs FCFS/MLFQ 17.5 avg response. |
| `staggered_short_arrival` | moderate | RR 4.5 vs others 7.0 avg response. |
| `burst_prediction_demo` | predictor-dependent | SJF/SRTF match FCFS at EMA cold-start; separate once the LLM supplies burst priors (see below). |
| `starvation_priority` | param-dependent | Needs Priority+Aging / MLFQ boost params to separate; flat under a generic RR guard. |

### Why SJF/SRTF sometimes match FCFS

The simulator (like the kernel) seeds `predicted_burst` from the EMA `initial`
prior at cold start — **it never reads `actual_bursts`** (the no-future-burst
rule, [`system_limitations.md`](system_limitations.md)). Until the LLM advisor
supplies per-process burst priors (or the EMA observes a few bursts), every
unseen process looks equally long, so SJF/SRTF degrade to arrival/ready order
and read like FCFS. This is expected, honest behaviour — not a bug.

## Honesty rules for workload JSON

- `cpu_bursts` are the **visible, planned** bursts; `actual_bursts` are the
  **true future** bursts. The workload analyzer strips `actual_bursts` from the
  features handed to the LLM (`tools/workload_analyzer.py`). Verified by
  `tests/test_workloads.py`.
- Every workload includes `id`, `description`, `target_metric`,
  `expected_behavior`, `schema_version`, and `processes`; most also include
  `expected_best_algorithm` as a theoretical hint (not enforced).
