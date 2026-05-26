# Counterfactual Metric View — Plan

Plan for a small read-only dashboard card that answers the audience
question "why does the LLM always pick MLFQ?" by showing what
algorithm **would** win if the target metric changed.

> Companion to `docs/algorithm_decision_diversity_audit.md` (which
> establishes the data) and `docs/recommendation_evidence_audit.md`
> (which inventories what the dashboard already shows). No code in
> this PR; just the spec for the follow-up PRs.

---

## 1. Problem this view solves

Every committed xv6 snapshot picks **MLFQ** with `SUCCESS` /
`regret_score=0.0`. The audit (`docs/algorithm_decision_diversity_audit.md`
§2) shows this is **genuinely correct** for the chosen target metric
`avg_response_time`, but **other algorithms win under other metrics**:

- `priority_sensitive` → **RR** wins `avg_waiting_time`,
  `avg_turnaround_time`, and `max_waiting_time`.
- `interactive` → **Priority** wins `avg_turnaround_time`.
- `mixed` → **RR** wins `max_waiting_time`.
- Every profile → MLFQ wins `avg_response_time` and `throughput`.

The audience cannot see this from the existing UI without reading
the audit doc. A small counterfactual card surfaces it directly.

## 2. Why MLFQ dominates `avg_response_time` (recap)

- The host-side `workload_analyzer.py` sets
  `target_metric = "avg_response_time"` on every profile today.
- The LLM's recommended MLFQ params (`queues=2`, `quantum=[10, 50]`,
  `aging_threshold=500`, `boost_interval=100`) put short jobs in
  the top queue and let long jobs drift down — minimizing response
  time on workloads where most bursts are short.
- xv6 traces are tick-granular and short (4–5 children, 1–8 tick
  bursts), which gives MLFQ a clean advantage and starves SJF/SRTF
  of the signal they need.

The view does **not** challenge this. It accepts MLFQ as the winner
for the current target and shows the rest.

## 3. Data the view needs (already exists)

Every snapshot's `metrics.json` carries a `comparison` block of the
form:

```jsonc
{
  "comparison": {
    "MLFQ":     { "avg_response_time": 0.0, "avg_waiting_time": 0.2,
                  "avg_turnaround_time": 2.4, "throughput": 0.312,
                  "max_waiting_time": 1,    "preemption_count": 4,
                  "starvation_occurred": false, "judgment": "SUCCESS" },
    "RR":       { ... },
    "FCFS":     { ... },
    "Priority": { ... },
    "SJF":      { ... },
    "SRTF":     { ... }
  }
}
```

That is enough. **No new field added to the data contract.** The
view recomputes best-per-metric on the client from existing rows.

## 4. Algorithm direction

Lower-is-better:
`avg_response_time`, `avg_waiting_time`, `avg_turnaround_time`,
`max_waiting_time`.

Higher-is-better:
`throughput`.

`preemption_count` is intentionally **excluded** from the view —
FCFS always wins it trivially (0 preempts) and that's not a quality
signal. The audit's §2 calls this out.

`starvation_occurred` — handled the same way the existing per-row
Judge handles it: if a candidate algorithm's row reports
`starvation_occurred=true`, it cannot be the "best" pick (mirrors
PR #14's rule). Falls through to the next-best in the candidate list.

## 5. UI: minimal-impact placement

Two viable spots:

| Option | Pros | Cons |
|--------|------|------|
| **A. New card in the left column**, between `RecommendationEvidence` and `EvaluationResult` | Same column as the recommendation/guard/evidence story; reads naturally top-to-bottom; the "Why this algorithm?" card sets up the question and this card answers the trade-off. | Adds a new row to the left column. |
| B. Extend `AlgorithmComparison.jsx` (right column) with a header strip | No new card. | The comparison table is already wide and dense; adding a strip would muddy the per-row Judge column. |

**Recommend A.** The left column has room (it grew by one card in
PR #32 with `RecommendationEvidence` and dashboards still build at
180.76 KB JS, well under any concern). The story flow becomes:

> Recommendation → Guard → **Why this algorithm? (evidence)** →
> **What if the goal changed? (counterfactual)** → Final evaluation.

## 6. Card spec

Label: **`Metric trade-off`**. Five-row, four-column table.

| Column | What | Source |
|--------|------|--------|
| Metric | human label (`Response time`, `Waiting time`, etc.) | hard-coded list, lowercase tied to the canonical key |
| Best   | algorithm name + small color dot | recomputed from `comparison` |
| Value  | best value, formatted (3 decimals for `throughput`, 2 for ticks) | `comparison[best][metric]` |
| vs LLM pick | `=`, `↑ better by X`, or `↓ worse by X` (relative to LLM-selected) | `comparison[LLM][metric]` |

One row per metric in order:

1. **Response time** (`avg_response_time`) — current target metric;
   render the row with a subtle highlight (left-border accent) and
   a small `target` pill so the audience knows which row currently
   drives the SUCCESS/FAIL verdict.
2. **Waiting time** (`avg_waiting_time`).
3. **Turnaround time** (`avg_turnaround_time`).
4. **Max waiting** (`max_waiting_time`).
5. **Throughput** (`throughput`).

Below the table: one short sentence like
`LLM-selected MLFQ wins 3 of 5 metric goals on this workload.` —
computed live; no overclaim if the count is 5/5 or 0/5.

## 7. Defensive rendering

- If `comparison` is missing or empty: render
  `Metric trade-off — not available for this snapshot.`
- If a metric is absent from a row, that row is skipped (not
  fabricated as 0).
- If every candidate has `starvation_occurred=true`, the row shows
  `(starvation)` instead of a winner.
- The card never reads or writes anything outside the loaded
  `metrics` prop. It does **not** add a new fetch.

## 8. PR sequencing

1. **P0-2** — add a small `computeBestPerMetric()` helper in
   `dashboard_live/src/data/schemaCompat.js` (right next to the
   existing `computeAlgorithmJudgment`). Unit-tested in PR review
   by reading the committed snapshot data and comparing against
   `scripts/analyze_algorithm_winners.py` output (which is the
   audit's source of truth).
2. **P0-3** — add `CounterfactualMetricView.jsx` and wire it in
   `App.jsx` between `RecommendationEvidence` and `EvaluationResult`.
3. **P1** — update `docs/presenter_script.md` and
   `docs/presentation_defense_notes.md` so Beat 5 / Q&A row points
   at the new card for "why always MLFQ?".

PRs 2 and 3 may be bundled if both are small and tightly coupled —
the helper exists only to serve the card; keeping them in one
coherent PR is acceptable.

## 9. Out of scope

- No scheduler / xv6 / orchestrator / validator changes.
- No data-contract expansion.
- No new LLM calls.
- No layout redesign — one card row added to the existing left
  column.
- Runtime correction stays Partial / Future Work.
