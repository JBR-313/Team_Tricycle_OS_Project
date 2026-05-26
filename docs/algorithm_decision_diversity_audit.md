# Algorithm Decision Diversity — Audit

Post-snapshot audit. Every committed xv6 profile snapshot
(`interactive`, `cpu_bound`, `mixed`, `priority_sensitive`) currently
shows the LLM picking **MLFQ** with `judgment=SUCCESS` and
`regret_score=0.0`. This document checks whether that uniformity is
a model bias, a metric-floor artifact, or genuinely correct, and
where real cross-algorithm diversity does exist in the data.

> Read alongside `docs/xv6_profile_support.md` (what's runnable on
> xv6) and `docs/recommendation_evidence_audit.md` (which evidence
> fields the dashboard already shows).

---

## 1. Why does the LLM pick MLFQ on all four profiles?

Three facts from the committed snapshots:

1. **Every workload uses `target_metric = "avg_response_time"`** —
   that's the host-side `workload_analyzer.py` default for
   interactive-tilted summaries and the LLM has been keying its
   recommendations off it. The recommendation card includes a
   one-line `target_metric` chip.
2. **xv6 workloads are short and tick-granular** — 4–5 children per
   profile, makespan in the 16–48 tick range. Burst values are
   small integers (1–8).
3. **The LLM's recommended MLFQ parameters** (`queues=2`,
   `quantum=[10, 50]`, `aging_threshold=500`, `boost_interval=100`)
   bias toward short interactive jobs in the top queue and let
   long jobs drift down — a configuration that minimizes
   `avg_response_time` on workloads where most jobs are short and
   the rest are CPU-bound.

So the LLM is not asserting "MLFQ for all workloads" as a general
truth. It is asserting "MLFQ minimises `avg_response_time` on
these specific small workloads," which the metrics back up.

## 2. Best algorithm per metric and profile (objective, from the snapshots)

Direct read of `comparison` block in
`dashboard_live/public/live-data/snapshots/<profile>/metrics.json`.
**Bold cell = best on that metric.**

| Profile / Metric        | resp     | wait     | turn     | thru     | max_wait | preempt |
|-------------------------|----------|----------|----------|----------|----------|---------|
| interactive             | **MLFQ** | **MLFQ** | Priority | **MLFQ** | **MLFQ** | FCFS    |
| cpu_bound               | **MLFQ** | **MLFQ** | **MLFQ** | **MLFQ** | **MLFQ** | FCFS    |
| mixed                   | **MLFQ** | **MLFQ** | **MLFQ** | **MLFQ** | RR       | FCFS    |
| priority_sensitive      | **MLFQ** | RR       | RR       | **MLFQ** | RR       | FCFS    |

Take-aways:

- **MLFQ wins `avg_response_time` on every profile.** That's the
  metric the LLM optimises for, and `regret_score = 0.0` is
  literally correct.
- **MLFQ also wins `throughput` on every profile.**
- **Real cross-algorithm diversity DOES appear**, just not on the
  default target metric:
  - `priority_sensitive` → RR wins `avg_waiting_time`,
    `avg_turnaround_time`, and `max_waiting_time`.
  - `interactive` → Priority wins `avg_turnaround_time`.
  - `mixed` → RR wins `max_waiting_time`.
- **FCFS trivially wins `preemption_count`** on every profile —
  FCFS is non-preemptive, so it always lands at 0 preempts.
  Not a meaningful "quality" signal.
- **SJF and SRTF never win** on any metric in any committed
  snapshot — see §3.

## 3. Is the uniform pick a workload-too-small / floor artifact?

Partly. Two safeguards we already shipped suppress sub-tick noise:

- `MIN_STARVATION_WAIT_TICKS = 5` in `tools/metrics.py` (PR #14) —
  prevents short xv6 traces from falsely flagging starvation.
- `JUDGMENT_ABS_FLOOR = 0.5` in `scripts/orchestrator.py:_judge`
  and `dashboard_live/src/data/schemaCompat.js` (PR #15) —
  prevents sub-tick gaps from collapsing the regret denominator
  to 1e-9 and forcing every non-best algorithm to `FAIL`.

These floors are doing their intended job. Without them, the
"close" rows above would either fail spuriously or claim ties
that are not real. With them, MLFQ winning by 0.0 means it is
either tied or genuinely better; the per-metric losers we list
in §2 lose by more than the floor and are therefore real losers.

What does suppress diversity on **xv6 specifically**:

- **5 children per profile.** SJF/SRTF need many short jobs to
  visibly out-perform RR; 4–5 children gives the burst predictor
  too little signal.
- **Bursts in 1–8 ticks.** The quantums in the kernel and the
  LLM's quanta in MLFQ are wider than most bursts, so a single
  child often runs to completion in one slice — eliminating the
  "preempt then queue" pattern where MLFQ vs RR would differ.
- **No I/O, no synchronisation, no priority inversion.** The
  profiles only test arrival/burst patterns. Realistic
  interactive vs CPU contention is not modelled.

The simulator path produces longer traces and `FAIL` /
`NEAR-SUCCESS` judgments more often (see
`scripts/multi_profile_demo_check.py --backend simulator`'s
summary), but the goal explicitly forbids presenting simulator
output as real xv6.

## 4. Is MLFQ genuinely best, then?

**On `avg_response_time` against these four workloads: yes.** The
LLM's recommendation tracks the data exactly. On `priority_sensitive`
and the `max_waiting_time` metric on `mixed`, **RR would beat MLFQ
if those were the chosen target metric** — the diversity exists,
it just doesn't surface in the default judgment because the target
metric does not change between profiles.

The honest framing for the demo is:

> "On the metric the LLM optimises for, MLFQ wins on every curated
> xv6 workload — and you can see that in the comparison table for
> each snapshot. If we changed the target metric, the winner would
> change for some profiles — for example, RR wins waiting,
> turnaround and max-waiting on `priority_sensitive`."

## 5. What safe change could produce a different LLM pick?

Without modifying scheduler semantics or implementing runtime
correction, three honest options:

1. **Pick a different target metric in the workload summary.**
   `workload_analyzer.py` already derives `target_metric`; a
   `priority_sensitive` workload could output
   `target_metric = "avg_waiting_time"` and the LLM would then
   plausibly recommend RR. This is a real, data-driven change,
   not a fake. (Out of scope for this audit PR; would be a
   follow-up that needs schema-side care.)
2. **Add an explicitly exploratory workload profile** with more
   children (e.g. 12–20) and more burst variance so SJF/SRTF
   can win on `avg_response_time` against MLFQ's static quantum
   choice. Must be marked dev/exploratory and not shipped as
   part of the final xv6 demo unless validated.
3. **Add the per-row `Best` column the audit table above already
   has.** Dashboard's `AlgorithmComparison.jsx` could surface the
   per-metric best directly so the audience sees diversity per
   metric instead of having to read this doc. Pure UI surface;
   data already supports it.

## 6. What this audit does NOT do

- It does not change scheduler semantics or the xv6 kernel.
- It does not change the existing metric/judgment rules.
- It does not implement runtime correction (still Partial /
  Future Work).
- It does not add new workload profiles, fabricate diversity, or
  inflate ties into "wins".
- It does not re-run the LLM advisor — every number cited above
  comes from the existing committed snapshots.

## 7. Action items (follow-up PRs)

- **P0-2**: add `scripts/analyze_algorithm_winners.py` that
  re-derives the table in §2 directly from
  `dashboard_live/public/live-data/snapshots/*/metrics.json` so
  the audit stays verifiable as the snapshots evolve. No data
  mutation, no LLM call.
- **P1 (optional, only if §5 option 2 is judged useful):** add a
  dev-only exploratory profile to the simulator path with more
  children + burst variance. Clearly flag as not-for-demo.
