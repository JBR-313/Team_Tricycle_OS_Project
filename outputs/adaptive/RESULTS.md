> **⚠ Provenance (historical):** the generator `experiments/adaptive_sched_eval.py`
> ran in the **Python scheduler simulator**, which has since been **removed** —
> xv6 is now the sole execution authority. These numbers are kept as a record of
> the negative result and are **no longer reproducible from this repo**. The xv6
> run is now deterministic (`-icount shift=3,sleep=off` + fixed-iteration
> `run_burst` + tick-aligned start; see `docs/GOAL.md`), so a *clean* re-measurement
> of adaptive switching on the real kernel is now feasible as future work.

# Does observe-then-adapt (ODA) beat the best STATIC scheduler? — measured (simulator, archived)

**Verdict: NO, not robustly.** On non-stationary workloads in the reference
simulator, mid-run adaptive switching gives at best a marginal (4–9%) gain over
the best static algorithm in an idealised cost-free model, the gain is NOT
reachable by an honest online decision rule, and it collapses to **zero** once a
realistic context-switch cost is added. This is an honest negative result.

## Setup
`experiments/adaptive_sched_eval.py` + `experiments/adaptive_workloads/*.json`.
Controlled A/B in the deterministic simulator (every arm = identical model).
Arms (lower metric = better):
- **B0** static default (the safe start, RR/PRIORITY)
- **B1** static oracle = best of all 6 static algorithms (the bar)
- **B2\*** oracle adaptive = start default, switch ONCE at the best (tick, algo)
  found by exhaustive sweep (the *ceiling* of single-switch adaptation)
- **B3** observed-rule adaptive = same, but the switch is decided online from
  ONLY the observed-so-far history (honest; never reads hidden remaining burst)

`switch_cost` = ticks burned on each context switch to a different process
(0 = the idealised cost-free simulator; ≥2 = a realistic kernel-like penalty).

## Result — avg_turnaround_time / avg_waiting_time, 4 workloads

| regime | switch_cost | headroom (B1−B2\*) | adaptive beats best static? | B3 (online rule) |
|---|---|---|---|---|
| RR-vs-FCFS (3 workloads) | 0 | +0.5 … +1.4  (≈4–9%) | technically yes, **marginal** | ties B1 or **worse** |
| RR-vs-FCFS (3 workloads) | 2 | **0** | **no** | ≤ B1 |
| RR-vs-FCFS (3 workloads) | 5 | **0** | **no** | ≤ B1 |
| priority-vs-batch | 0 / 2 / 5 | **0** | **no** (MLFQ/FCFS dominate) | ≤ B1 |

At `switch_cost ≥ 2` the oracle "adaptive" choice degenerates to *switch at tick 0*
— i.e. just run the single best static algorithm (FCFS) the whole time. Headroom 0.

## Why (root cause, three reasons)
1. **Strong generalist statics.** MLFQ is itself adaptive (multi-level feedback),
   and SJF/SRTF are predictive. They already sit at/near the per-instance ceiling,
   so a single mid-run switch has almost nothing to add.
2. **One switch, fixed start.** A single switch with a fixed safe default can fix
   only the *post-switch* phase; if the default is wrong for Phase A you have
   already lost it, and you cannot get both phases right.
3. **Context-switch cost favours one low-overhead algorithm globally.** The
   non-stationarity I could construct (responsiveness phase vs batch phase) relies
   on RR's interleaving being good in Phase A — but RR's interleaving IS the
   switching that a realistic cost penalises. With a cost, FCFS (fewest switches)
   becomes best for the *whole* run, erasing the regime advantage. The headroom
   adaptive scheduling exploits in real systems comes mostly from costs/effects
   (cache, NUMA, I/O overlap) this single-core tick simulator does not model.

## What this means for the project
- **Do NOT build the demo around "the LLM adapts mid-run and beats the best
  static scheduler."** Measurement does not support it here — same shape as the
  earlier "LLM picks the best algorithm" negative result. In this clean,
  single-core, brute-forceable xv6 setting, a good *static* (or the inherently
  adaptive MLFQ) is hard to beat, whether by LLM selection OR by mid-run switching.
- The honest, measured-POSITIVE story is unchanged and still the right one:
  (1) **safety net** (Guard + post-evaluation correction reverses a bad pick),
  (2) **burst-prediction win** (LLM priors cut SRTF avg-waiting, see
  `outputs/ablation/burst_scheduling_RESULTS.md`),
  (3) **feedback improves recommendation** (`outputs/learning/RESULTS.md`).
- This negative result is itself presentable: "we tested adaptive switching,
  measured that strong static baselines + switch costs leave no robust headroom in
  this setting, and explained why — so we did not overclaim it." Honest negative
  results with a mechanism beat a contrived win.

## Caveats / where it COULD still hold (not pursued)
- A simulator that models context-switch / cache cost explicitly, or **real xv6**
  where those costs are physical, might expose headroom RR-vs-FCFS hides here.
- Multi-core, or workloads too large to brute-force, change the economics (you
  cannot just run all 6 and pick best). Single-switch → multi-switch online control
  is a different (harder) problem.
- These are constructed workloads; this is a capability probe, not proof about
  real workloads either way.

Reproduce: `python3 experiments/adaptive_sched_eval.py --switch-cost 0` (then 2, 5),
and `… priority_then_batch --start PRIORITY --metric avg_waiting_time`.

## (b) Real xv6 — ATTEMPTED, BLOCKED by metric non-determinism
The idealised simulator lacks context-switch cost, so the natural follow-up was to
measure adaptation on real xv6 where that cost is physical. Before building a kernel
mid-run switch, `experiments/xv6_determinism_probe.py` checked the prerequisite: is
the real-xv6 metric pipeline even reproducible? It is NOT.

Running the identical (profile, algo) three times via the orchestrator's exact
QEMU + parse + metrics path:

| profile / algo | avg_turnaround across 3 reps |
|---|---|
| convoy_tail / rr   | 7.83, 9.57, 9.71  (~24% spread) |
| preempt_stream / srtf | 22.33, 23.33 |
| convoy_tail / **fcfs** | 24.71, 25.71  (**non-preemptive, still varies**) |

FCFS (a deterministic schedule) varying proves the noise is in the WORKLOAD model,
not the scheduler: `schedtest`'s `run_burst()` consumes CPU by wall-clock spinning
(`while(uptime() - start < ticks)`), so under QEMU host-timing jitter a "6-tick
burst" actually consumes 6 or 7 ticks, run to run. Burst lengths jitter by ±1 tick
and that propagates into every metric.

**Consequence:** the per-run noise (~several %, often ±1 tick on 7–25-tick metrics)
is as large as or larger than the adaptive headroom the simulator predicted (4–9%
idealised, 0 with switch cost). A trustworthy adaptive A/B on real xv6 is therefore
not achievable with the current harness — building the kernel switch would produce
numbers we could not honestly cite (the same trap the earlier burst `--hints` xv6
confirmation fell into). This is a statement about *measurability with this harness*,
not proof that adaptation cannot help on real hardware.

To make (b) measurable one would first have to make `schedtest` bursts deterministic
(e.g. fixed iteration counts calibrated to ticks, decoupled from `uptime()`), or run
much longer workloads + many reps per arm — a harness redesign whose payoff is
bounded by the simulator's already-near-zero headroom. Not pursued.

## Overall conclusion
Across the idealised simulator, the cost-augmented simulator, AND the real-xv6
feasibility probe, **mid-run adaptive switching is not a demonstrable win in this
project's setting.** It joins "the LLM picks the best algorithm" as a measured,
explained negative result. The defensible, measured-positive story remains: safety
net + burst-prediction SRTF win + feedback-improves.
