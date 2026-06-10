# GOAL 2 — clean, statistical, real-kernel test of LLM burst prediction

## Question
Does the LLM's cold-start burst prior improve SJF/SRTF scheduling vs a blind EMA
cold start — **leak-free, on real xv6, across a distribution of random
workloads** (not 5-10 hand-made ones)? This is the project's first chance at a
clean POSITIVE result for "the LLM improves the scheduler," now that xv6 is
deterministic ([GOAL.md](GOAL.md)).

## Why this design
The earlier simulator A/B win was contaminated three ways: a `description` leak
in the prompt, simulator-only execution, and overfit to a tiny curated set. This
fixes all three: leak closed, real kernel, random workload distribution with CIs.

## The make-or-break rule (do NOT relocate the leak)
The random generator must make burst a **noisy** function of a HIDDEN type, and
the visible features (arrival/priority/io_count/burst_count) a **realistic,
imperfect** signal of that type — like real workloads. NEVER a deterministic
feature→burst map (that just moves the description leak into the generator). The
hidden type and actual bursts are used to GENERATE + SCORE only, never put in a
prompt (same contract as `actual_bursts`).

## Determinism note
xv6 is now reproducible, so repeating the *same* workload is pointless (identical
output). Statistical power comes from generating MANY DIFFERENT workloads;
aggregate mean ± CI over the distribution.

## Steps
1. **schedtest `--procs`**: inject an arbitrary workload at runtime
   (`--procs "arrival:burst:prio,..."`) instead of the fixed C tables, so random
   workloads run on the real kernel. Preserve the fork-order == index invariant.
2. **Workload generator** (host-side Python): a SIGNAL set (burst = noisy(hidden
   type); features = imperfect signal) and a NEGATIVE-CONTROL set (burst
   independent of features). Seeded, writes v2 JSON with `actual_bursts`.
3. **Close the leak**: add `description` (+ `id`) to `_PROMPT_STRIP_KEYS` so no
   free-text answer-key reaches the burst/advise prompt.
4. **A/B harness**: for N generated workloads × strategies {ema_cold, heuristic,
   llm} × {SJF, SRTF}, run on xv6 via `--procs` (+ `--hints` priors), parse,
   compute metrics. Report mean % improvement of llm vs ema and pairwise ordering
   accuracy, with CIs, SEPARATELY for signal vs control.

## Done when
- random workloads execute on xv6 via `--procs` (verified), AND
- the prompt provably contains no `description`/`actual_bursts`/`type`, AND
- the harness reports, over N workloads: LLM-vs-EMA on the SIGNAL set, AND the
  NEGATIVE CONTROL shows the LLM does NOT win (≈ tie) — the built-in leak detector.

## Honest outcome range
- Positive: LLM beats EMA on signal set, ties on control → clean real-kernel win.
- Null: LLM ties on both → visible features carry too little leak-free signal.
Either is publishable; the control set is what makes the result trustworthy.
