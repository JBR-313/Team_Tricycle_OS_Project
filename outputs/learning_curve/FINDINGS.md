# Adaptive learning from recurring workload patterns — findings

**Question.** Local-device users run recurring workload *patterns*. If an LLM
advisor learns from that repetition (retrieval-augmented prompting over past
measured outcomes), does scheduling-recommendation quality measurably improve —
and does a *change* in the pattern (drift) need explicit correction?

**Method.** Real xv6 backend (no simulator). 4 discriminating workload families
× 5 jittered instances, each swept once over the 4 core algorithms
(RR / FCFS / Priority+Aging / MLFQ) via `schedtest --procs`. The 20-instance
*bank* (`bank.json`) is then **replayed offline** in different orders — repetition
and drift are modelled by replay order, so no instance is re-run.
y-axis = **regret** = normalised gap from the measured-best on each instance's
target metric (0 = matched best). Harness: `experiments/learning_curve_{bank,replay,llm}.py`.

The families have **different winners** (MLFQ wins interactive + convoy; FCFS
wins cpu_batch + priority), so no single "always X" dominates — this is *not*
information-bounded the way an all-one-family set would be.

## Result 1 — repetition improves recommendations (CONFIRMED)

knn regret vs how many **same-family** precedents were already in the store when
each instance was advised (the order-independent intuition test):

| same-family precedents seen | mean regret |
|---|---|
| 0 (cold / just drifted) | **0.283** |
| ≥ 1 | **~0.0** |

Seeing the pattern **once** before is enough to go from "guessing" to near-optimal.

| arm | mean regret |
|---|---|
| fixed_rr (no learning) | 0.380 |
| fixed_mlfq (best "always X") | 0.215 |
| **knn (cumulative retrieval)** | **0.059** |
| llm_facts (LLM, no memory) | 0.327 |
| **llm_retrieval (LLM + precedents)** | **0.099** |

- Pure retrieval signal (knn) beats the best fixed bar **3.6×**.
- At the interface, **llm_retrieval beats llm_facts 3.3×** and also beats the
  fixed bar — the LLM genuinely exploits the accumulated signal in-prompt.
- llm_retrieval (0.099) sits slightly above pure knn (0.059): LLM reasoning adds
  some noise on top of retrieval. Honest reading: **the signal lives in
  retrieval; the LLM is the interface** — consistent with the project thesis
  (LLM out of the hot path, LLM at the human interface).

## Result 2 — signal is real, not an artifact (negative control PASSES)

Shuffle the stored `measured_best` labels (destroy the feature→winner relation):

| condition | knn mean regret |
|---|---|
| true labels | 0.059 |
| **shuffled labels** | **0.314** (worse than the fixed bar) |
| best fixed bar | 0.215 |

The edge collapses — actually inverts — under shuffling, so the gain is *learned
signal*, not classifier skill or an ordering artifact.

## Result 3 — drift does NOT need explicit correction here (honest negative)

Recovery after a pattern change is **immediate**: one same-family precedent drops
regret 0.283 → ~0. So an explicit drift-detection arm (`knn_drift`: detect a
novel query, fall back to the robust default) adds nothing on `stable_blocks`
(0.059 = 0.059) and *hurts* on the high-churn `round_robin` (0.118 vs knn 0.083)
— the system self-heals faster than a correction layer can help. This matches the
project's earlier "no mid-run headroom" finding.

**Caveat (honesty).** Families here are highly feature-separable and each family's
winner is rock-stable, so recovery is trivially fast. Subtler real-world drift
(slow distribution shift, unstable winner) may behave differently — this setup
shows drift correction is *unnecessary here*, not that it is useless in general.

## Integration

Shipped as an **opt-in** layer mirroring `--use-feedback` (default OFF keeps the
demo deterministic):

- **Accumulate (always-on):** `scripts/orchestrator.py` step `[8b] persist_outcome`
  appends every evaluated run's `(visible_features → measured_best)` to
  `outputs/learning/outcome_store.jsonl` (prompt-safe features only).
- **Consume (opt-in):** `orchestrator … --use-retrieval` → passes
  `--retrieval-store` to `tools/llm_advisor.py`, which injects the k most similar
  past outcomes into the advise prompt (`build_retrieval_block`, leave-one-out by
  name; no future-burst leakage).
- **No drift mechanism added** (Result 3).

Demo recipe: run a few real workloads to fill the store, then re-run with
`--use-retrieval` to show the warm-started recommendation.
