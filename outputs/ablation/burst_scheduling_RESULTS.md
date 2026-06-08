> **⚠ Provenance (historical):** the generator `experiments/burst_scheduling_eval.py`
> ran in the **Python scheduler simulator**, which has since been **removed** —
> xv6 is now the sole execution authority. These numbers are kept as a record and
> are **no longer reproducible from this repo**. Note two known caveats this run
> carried: it was simulator-only, and the burst-prediction prompt leaked the
> workload `description` (see prior analysis). The deterministic xv6 path now makes
> `experiments/burst_xv6_confirm.py` the live route to a *clean* real-kernel number.

# Does the LLM's burst prediction improve ACTUAL scheduling? — measured (simulator, archived)

`burst_ablation.md` showed the LLM wins on burst *ordering* (0.90 vs 0.50). This
closes the loop the project never measured: feed each prediction strategy's
priors into SJF/SRTF and measure the real schedule (avg waiting time). It is the
one place the LLM can produce a measurable *performance* win, because SJF/SRTF
schedule by predicted burst.

## Method — controlled A/B in the reference simulator
`experiments/burst_scheduling_eval.py`. Same workload, same simulator; the ONLY
difference between arms is the cold-start burst priors:
- **ema_cold**: one constant for everyone (the blind cold start) — SJF/SRTF
  cannot tell jobs apart, so they degenerate toward arrival order. Honest "no
  LLM" baseline; for single-burst jobs the kernel EMA never refines, so a
  constant is faithful.
- **llm**: the LLM's per-process prediction (visible features only, cached in
  `llm_predictions.json`).

Because both arms run the identical deterministic model, the metric delta
isolates prediction quality alone. The simulator's absolute fidelity to xv6 is
irrelevant to a within-simulator A/B.

## Result (10 workloads: 5 simulator + 5 xv6 mirror profiles)

| algorithm | avg_waiting | turnaround | response | llm better / worse / tie |
|---|---|---|---|---|
| **SRTF** | **+30.0%** | +22.3% | +32.5% | **5 / 1 / 4** |
| SJF | +6.6% | +5.0% | +6.5% | 2 / 1 / 7 |

Per-workload SRTF avg-waiting improvement (positive = LLM better):

| workload | LLM priors | Δ avg_wait | note |
|---|---|---|---|
| bursty_long_tail | [10,2,2,2,2] | **+89.6%** | LLM isolates the one long job |
| staggered_short_arrival | [2,10] | **+73.5%** | |
| convoy_effect | [10,100] | **+71.5%** | LLM flags the long job |
| xv6_prio_starve | [10,1,1,1,5,5,1] | **+66.7%** | only heterogeneous xv6 profile |
| burst_prediction_demo | [10,50,100] | +17.1% | |
| xv6_convoy_tail, xv6_bimodal, xv6_burst_storm, xv6_preempt_stream | uniform [10,…] | 0% (tie) | LLM correctly cannot differentiate |
| **short_jobs** | **[10,15,12,…] (spurious)** | **−18.0% (WORSE)** | all jobs are 1 tick; LLM invents an ordering that does not exist |

## What this proves (honest)
**The LLM's burst prediction measurably improves SRTF scheduling — by up to
~90% avg waiting time — on workloads whose VISIBLE features let it tell short
jobs from long ones (5 of 10, mean +30%).** It is a tie on the 4 homogeneous
xv6 profiles where the LLM correctly returns a uniform guess.

**But it is NOT free of failure.** On `short_jobs` — where every job is genuinely
1 tick — the LLM does NOT recognise the homogeneity; it invents a spread
([10,15,12,…]) and SRTF reorders identical jobs on that false signal, making avg
waiting **18% WORSE** than the blind EMA. So the honest tally is **5 better, 1
worse, 4 ties**, not "never worse." The lesson is precise: the LLM prior helps
exactly when there is real, visible burst heterogeneity to exploit, and it can
hurt when it over-differentiates jobs that are actually equal. A guard that falls
back to EMA when predicted variance is low would capture the wins and drop this
loss — a concrete next step.

The win lives inside the SJF/SRTF use case (predictive scheduling), which is not
the best overall algorithm on most xv6 profiles (RR/MLFQ are). So this is a
*within-algorithm* performance win, not "the LLM makes the system fastest
overall."

SJF gains less than SRTF because SJF is non-preemptive: once a job starts it runs
to completion, so cold-start ordering matters only at simultaneous dispatch.

## A note on reproducibility
The `bursty_long_tail` entry in `llm_predictions.json` was once cached as a
uniform `[10,…]` (a one-off bad elicitation during the bulk xv6 run). Re-eliciting
live with the shipped prompt is deterministic (temp=0) and returns the
differentiated `[10,2,2,2,2]` shown above on every run, which is what these
numbers use. Regenerate with `python3 experiments/burst_ablation.py --advise
--workloads bursty_long_tail` then `python3 experiments/burst_scheduling_eval.py`.

## xv6 confirmation — ATTEMPTED, INCONCLUSIVE (do not cite numbers)
`experiments/burst_xv6_confirm.py` ran the same A/B on the real kernel. The EMA
arm was stable across reruns (e.g. prio_starve SRTF avg_wait = 23.5 both times),
but the **--hints arm was non-deterministic** (prio_starve SRTF llm = 20.67 then
6.14; convoy_tail llm = 18.0 then 16.14 with *identical* all-10 hints). The
instability tracks the trace-capture path under heavier preemption output, not
the kernel schedule, so these xv6 numbers are unreliable and were discarded. The
controlled simulator A/B above is the reliable measurement. Hardening the xv6
capture (reuse the orchestrator's full windowing, longer RUN_END settle) is the
follow-up needed to land a real-kernel number.

## For the presentation
- **Honest performance win**: "LLM burst priors cut SRTF average waiting time by
  up to ~90% (mean +30% over 10 workloads) when the workload has visible burst
  heterogeneity — measured by controlled A/B in the reference simulator." Pair
  with the ordering result (0.90 vs 0.50).
- **Be honest about the failure**: on a fully homogeneous workload the LLM
  over-differentiates and SRTF gets 18% worse (1 of 10). State it; it motivates
  the low-variance→EMA fallback guard.
- Do NOT claim an xv6-kernel number yet (capture path is non-deterministic).
- Do NOT claim it makes the system fastest overall — it improves SJF/SRTF
  specifically, where burst prediction is the scheduling input.
