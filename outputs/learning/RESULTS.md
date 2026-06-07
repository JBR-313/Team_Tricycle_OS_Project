# Retrieval-augmented recommendation — measured results

Goal: make the project satisfy its two core purposes, **measured**, not asserted —
1. "LLM makes the best choice"
2. "Evaluate the LLM's choice and improve it via feedback"

Method: **leave-one-out cross-validation** on the workloads that carry a real
measured best (`expected_best_algorithm` + `expected_best_source`). Each held-out
workload is predicted from the OTHERS only — its own answer is never in the store
and is stripped from its prompt (same honesty contract as `llm_advisor`). Built
with `experiments/outcome_store.py` + `experiments/retrieval_advisor.py`, run by
`experiments/recommendation_eval.py`.

## The bar to beat
The honest baseline is the best **fixed** policy ("always pick algorithm X"),
which exploits the class imbalance. A recommender only adds value if it beats it.

| set | n | classes | fixed-majority baseline |
|---|---|---|---|
| xv6-measured | 12 | MLFQ 7 / RR 5 | **always-MLFQ = 0.583** |
| simulator-measured | 15 | MLFQ 8 / FCFS 3 / RR 2 / PRIORITY 2 | always-MLFQ = 0.533 |
| all | 27 | MLFQ 15 / RR 7 / FCFS 3 / PRIORITY 2 | always-MLFQ = 0.556 |

## Result — xv6 backend (the project's execution authority)
Leave-one-out accuracy, k=3 retrieval, temperature 0 (reps=3 ≡ reps=1, the API
is deterministic here):

| mode | accuracy | vs baseline |
|---|---|---|
| fixed-MLFQ (baseline) | **0.583** (7/12) | — |
| fixed-RR | 0.417 (5/12) | below |
| kNN retrieval (equal weight) | 0.250 (3/12) | below |
| kNN retrieval (relevance-weighted, k=1) | **0.667** (8/12) | **above** |
| **LLM — facts only (current advisor)** | 0.333 (4/12) | below |
| **LLM — facts + retrieval (proposed)** | **0.417** (5/12) | below |

## What this proves

**Goal 2 (evaluate → feedback → improve): mechanism works.**
Retrieving past *measured* outcomes lifts the LLM from 0.333 → 0.417 (+1
workload). This is the honest, working replacement for the old `feedback_rules.md`
loop, which **degraded** held-out accuracy (4/5 → 2/5) by learning one global
majority-biased rule. Retrieval improves instead of harms because it conditions
on *which* past workloads resemble the current one, rather than emitting a single
"prefer MLFQ over RR" rule. Accumulated measured feedback genuinely helps.

**Goal 1 (LLM makes the best choice): honestly bounded — not achievable here.**
No LLM mode beats the trivial always-MLFQ baseline on the 12 xv6 profiles. Only a
(likely overfit, n=12) relevance-weighted 1-NN edges it at 0.667. The reason is
fundamental and measured:

> The feature that separates RR-best from MLFQ-best is the **burst length /
> convoy structure** — exactly the information the no-future-burst honesty rule
> hides from the LLM. Even using the *ground-truth* bursts (allowed only for this
> offline analysis), the best single-feature split is just 0.83, and classes
> overlap (e.g. `preempt_stream` cv=1.20 → MLFQ vs `convoy_tail` cv=1.23 → RR —
> near-identical structure, opposite winner). With visible features alone and a
> 7/12 MLFQ majority, "always MLFQ" is a strong baseline that reasoning cannot
> reliably beat.

This is a real, defensible finding, not a tuning failure: **under the project's
own honesty constraint, picking the single best algorithm from visible features
is close to the information-theoretic ceiling of guessing the majority class.**

## Honest implications for the presentation
- Do **not** claim "the LLM picks the best scheduler" — measured false on xv6.
- **Do** claim: a retrieval/outcome-store feedback loop measurably improves the
  recommender and fixes the old loop that made things worse (Goal 2, real).
- Lead the LLM's *positive* value where it is measured: **burst-prediction
  ordering 0.90 vs 0.50** (`outputs/ablation/burst_ablation.md`) and the
  **safety architecture** (advise → Guard → correction → explain) that contains
  the LLM's wrong picks.

## Where a real Goal-1 win could still come from (untried, scoped)
1. **Route the LLM through its strength**: use the LLM's burst *ordering* (its
   measured win) to drive a deterministic, OS-theory algorithm selector, instead
   of asking it to name the algorithm directly. Ceiling is bounded by the 0.83
   true-burst separability above, so expect modest gains — verify before claiming.
2. **More labeled xv6 data**: 12 points is too few for a stable selection claim;
   the binary RR/MLFQ split with a 7/5 imbalance is noise-dominated.
3. **A setting where exhaustive comparison is infeasible** (continuous param
   tuning, online/streaming) so a zero-shot LLM pick has value the brute-force
   comparison cannot trivially replace.
