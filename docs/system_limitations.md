# System Limitations

Honest, explicit limits of the LLM Sched Copilot. These are by design (it is an
educational scheduling lab, not a production scheduler). State them plainly in
the demo and defense.

## Kernel / execution

- **CPUS=1 only.** The kernel runs single-hart. Dynamic scheduler params and
  `ticks_in_level` are written without `p->lock` from `trap.c`; this is safe
  only because the scheduler (the other writer) runs with interrupts off on one
  CPU. On CPUS>1 this would need locking. (`xv6-riscv/kernel/trap.c:30`.)
- **Curated xv6 workloads.** xv6 has **no JSON parser**. `schedtest.c` carries a
  fixed set of curated workload tables — six profiles: `interactive`,
  `cpu_bound`, `mixed`, `priority_sensitive` (≈5 procs each) plus the larger
  8-proc `interactive_storm` and `batch_convoy`. Arbitrary `workloads/*.json`
  run on the **simulator** only. The orchestrator maps each curated profile to a
  mirror JSON so burst priors align to fork order; `tests/test_xv6_mirror_alignment.py`
  enforces that the C tables and their mirrors stay in lockstep. See
  [`workload_coverage_matrix.md`](workload_coverage_matrix.md).
- **No kernel LLM.** The LLM never runs inside the kernel and never selects the
  next process at a timer tick. xv6 is the execution authority.
- **Two PID namespaces on xv6.** `workload_summary`/`recommendation` use 1-based
  workload-definition PIDs; `trace_*.jsonl`/`metrics` use kernel runtime PIDs
  assigned by `fork()` (the `schedtest` harness is one PID, each workload process
  a forked child). They are bridged by `BURST_HINT_APPLIED.index`↔`pid`, and
  `metrics.process_count` is `N+1` (it counts the harness parent).

## Scheduling semantics

- **SJF/SRTF are limited by the no-future-burst rule.** Future CPU bursts
  (`actual_bursts`) are never given to the LLM or the kernel. SJF/SRTF schedule
  on a *predicted* burst (EMA, optionally seeded by LLM priors derived from
  visible features). At cold start every unseen process shares the same
  `initial` prior, so SJF/SRTF degrade to arrival/ready order and can look like
  FCFS — and **SRTF may show no preemption**. This is expected, not a bug.
- **Aging/boost are round-granular**, not strictly tick-accurate — a
  simplification for the lab.
- **`--seed` only labels an xv6 run.** xv6 has no PRNG in `schedtest.c` (curated
  tables are fixed in C) and the run is reproducible (deterministic `-icount`
  clock), so the same (profile, algorithm, seed) reproduces exactly — `--seed`
  does not change the schedule. Statistical power therefore comes from generating
  many *different* random workloads (see `experiments/burst_random_eval.py`), not
  from re-seeding one profile.

## Pipeline / correction

- **Runtime correction is a host-side post-evaluation loop**, not live kernel
  control. After a run is evaluated, the orchestrator may launch a *second*
  ordinary xv6 run with a corrected, Guard-approved algorithm/params and record
  the before/after in `correction_applied.json`. There is **no** tick-level
  online correction and **no** in-kernel LLM call.
- **Simulator correction is an intentional no-op.** The apply loop re-runs the
  real kernel; on the simulator backend it records `applied:false` with a clear
  reason.
- **Feedback is FAIL-only and never faked.** Rules are generated only on a FAIL
  judgment (or starvation). With no `UPSTAGE_API_KEY` the step logs an explicit
  skip instead of inventing rules.

## Interface / UX

- **No websocket / live streaming.** The dashboard polls `manifest.json` for
  version changes; it does not stream kernel state live.
- **Simulator output is not proof of xv6.** The data-source badge
  (`XV6 TRACE` / `SIMULATOR` / `FALLBACK` / `SNAPSHOT`) exists precisely so
  simulator or fallback data is never mistaken for a real kernel run.
- **Offline fixture ≠ live LLM.** With `--offline-fixture` (and no key) the
  recommendation comes from committed fixtures and the manifest is stamped
  `metadata_source = demo_fallback`.

## Scope

- **Educational, not production.** Short, tick-granular runs; small process
  counts; a teaching-oriented set of algorithms. Not tuned or hardened for a
  real OS workload.
