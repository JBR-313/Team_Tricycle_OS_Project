# Recommendation Evidence — Audit

Post-RC audit of what evidence the recommendation pipeline already
publishes, what `dashboard_live` already shows, and what would help an
audience answer "why did the LLM choose this algorithm?" without a
broad UI redesign.

> Scope: read-only. No code/UI changes in this document.

---

## 1. Evidence already in the live-data JSON

All paths are relative to `dashboard_live/public/live-data/`.

### `recommendation.json` (Solar Pro 3, then guard-rewritten if rejected)

| Field | Example | Source |
|-------|---------|--------|
| `algorithm` / `recommended_scheduling_algorithm` | `"MLFQ"` | LLM |
| `params` | `{queues: 2, quantum: [10, 50], aging_threshold: 500, boost_interval: 100}` | LLM |
| `target_metric` | `"avg_response_time"` | LLM |
| `reason` | full sentence — _"The workload is entirely interactive with short bursts (avg 1.52) and no CPU-bound processes, so MLFQ with two queues and small quanta (10, 50) provides excellent response time and fairness. Aging and periodic boosts prevent any potential starvation..."_ | LLM |
| `confidence` | `0.95` | LLM |
| `_meta.model` | `"solar-pro3"` | LLM Advisor |
| `_meta.generated_at` | ISO timestamp | LLM Advisor |
| `_meta.workload_summary` | absolute path | LLM Advisor |

### `guard_decision.json`

| Field | Example |
|-------|---------|
| `guard_result` | `"accepted"` / `"rejected"` |
| `algorithm` / `scheduling_algorithm` | `"MLFQ"` |
| `params` | (passed-through or fallback) |
| `target_metric` | `"avg_response_time"` |
| `compatibility_score` | `0.95` |
| `confidence_score` | `0.95` |
| `reason` | `"Accepted: MLFQ is suitable for response_time (compat=0.95, confidence=0.95)."` |
| `fallback_used` | `false` (true ⇒ RR substituted) |
| `original_recommendation` | the LLM's original pick before guard |
| `_meta.source` | `"tools/algorithm_guard.py"` |

### `workload_summary.json` (host-side `workload_analyzer.py`)

| Field | Example |
|-------|---------|
| `process_count` | `25` |
| `avg_arrival_gap` | `1` |
| `cpu_bound_ratio` | `0.0` |
| `interactive_ratio` | `1.0` |
| `avg_priority` | `1` |
| `priority_variance` | `0` |
| `has_starvation_risk` | `false` |
| `burst_count_distribution` | `{min: 1, max: 2, avg: 1.52}` |
| `total_cpu_work` | `38` |
| `workload_file` | `"workloads/interactive_heavy.json"` |

### `metrics.json` (top-level only — full per-process omitted here)

| Field | Example |
|-------|---------|
| `scheduling_algorithm` | `"MLFQ"` (LLM-selected) |
| `judgment` | `"SUCCESS"` / `"NEAR-SUCCESS"` / `"FAIL"` |
| `regret_score` | `0.0` |
| `starvation_occurred` | `false` |
| `avg_response_time`, `avg_waiting_time`, `avg_turnaround_time`, `throughput`, `max_waiting_time`, `preemption_count` | scalars |
| `comparison[algo]` | per-algo metric row, with its own `judgment` |
| `best_algorithm` | `null` for the xv6 backend today (set by simulator path; orchestrator's `_judge` does not back-fill it) |

---

## 2. What `dashboard_live` already shows

Located in `dashboard_live/src/components/`, wired in `App.jsx`:

| Card | What it surfaces |
|------|------------------|
| `LLMRecommendation` | algorithm pill, target pill, params line, **reason clipped to 3 lines** (`-webkit-line-clamp: 3`) |
| `AlgorithmGuard` | result pill (`ACCEPTED` / `REJECTED`), fallback flag, **reason on one line with ellipsis** (`white-space: nowrap`), four hard-coded check pills (`✓ algo implemented`, `✓ params in range`, `✓ no fallback`) |
| `WorkloadSummary` | workload-type pill, process count, target pill, CPU/IA process counts derived from ratios, optional `main_risks` pills, starvation-risk pill |
| `EvaluationResult` | judgment, regret, starvation, target, best algo, LLM selected, Δ vs best, four per-metric chips (RT/WT/TAT/THRU) |
| `AlgorithmComparison` | one-row-per-algorithm table with `Judge` column re-derived from the selected metric |
| `LLMExplanation` | after-run natural-language explanation from `trace_explanation.json` |

Header bar also exposes backend badge, manifest version, seed, workload,
algorithms-executed count, total trace event count.

---

## 3. What is missing for audience understanding

These are gaps an audience member could plausibly notice during a
3-minute walk-through:

1. **LLM `reason` is clipped to 3 lines, Guard `reason` to one ellipsised
   line.** The actual reasoning is often longer than the clamp permits.
   The audience cannot see _why_ the LLM picked MLFQ without opening
   the JSON file.
2. **LLM `confidence` (e.g. 0.95) is not surfaced anywhere.** It is in
   `recommendation.json` but no card reads it.
3. **Guard `compatibility_score` / `confidence_score` are not surfaced
   either.** The Guard card shows the result text but not the numeric
   compat/confidence the guard recorded.
4. **`workload_summary` traits that the LLM actually keyed off** —
   `interactive_ratio`, `avg_arrival_gap`, `burst_count_distribution`,
   `priority_variance`, `total_cpu_work` — are partially shown
   (`interactive_ratio` → IA chip) but the others aren't visible. Yet
   the LLM's `reason` explicitly cites e.g. `"short bursts (avg 1.52)"`.
   An audience can't cross-check the LLM's claim against the data on
   screen.
5. **Provenance is hidden.** `_meta.model = "solar-pro3"` (and
   `metadata_source = "demo_fallback"` when the API is down) are not
   displayed beyond the backend badge's three states. A "Recommended by
   solar-pro3" / "Recommended by demo fallback" line would close the
   loop.
6. **No single "Why this algorithm?" view.** The relevant fields exist
   in three separate cards (`WorkloadSummary` → `LLMRecommendation` →
   `AlgorithmGuard`) plus the header. The audience has to reconstruct
   the story themselves.

---

## 4. Safe improvements possible without a redesign

These are options for follow-up PRs in this goal. Each touches a
single component or one small new card; the data contract does not
have to expand because every field already exists.

| # | Change | Risk | Scope |
|---|--------|------|-------|
| A | Lift the 3-line / nowrap clamps on `LLMRecommendation.reason` and `AlgorithmGuard.reason` — switch to a vertical scroll inside the existing card height. | Low. CSS only. | `LLMRecommendation.jsx`, `AlgorithmGuard.jsx` |
| B | Surface `confidence` (LLM) and `compatibility_score` / `confidence_score` (guard) as small numeric pills inside the existing cards. | Low. New chips in existing rows. | same two files |
| C | Add a compact new card "Recommendation Evidence" between `LLMRecommendation` and `AlgorithmGuard` that consolidates: workload profile + target metric + 3 most-relevant traits (`interactive_ratio`, `burst_count_distribution.avg`, `avg_priority`) + LLM reason + guard verdict + metrics judgment. Read-only. | Medium-low. New file; existing column layout permits one more card. | new `RecommendationEvidence.jsx`, one line in `App.jsx` |
| D | Surface provenance: render `_meta.model` (LLM) and `_meta.source` (guard) in small monospace text under the respective card title. | Low. | same two files |
| E | Graceful missing-field handling: every read should `?.` or default to "not available" so a partial JSON (e.g. older live-data) doesn't crash the dashboard. | Low. | all four evidence cards |

The recommended sequence for follow-up PRs in this goal:

1. Add option C (new compact `RecommendationEvidence` card) — biggest
   audience-understanding win, single file added, single line in
   `App.jsx`. Existing data contract unchanged.
2. Combine A + B + D in a second PR — tighten the existing cards so
   they no longer hide their own data.
3. Apply E as a defensive pass in a third PR — guards against the
   fallback / demo-fallback paths where some fields are missing.

`dashboard_live` layout (3 columns) already has room for one more
small card in the left column; no layout redesign required.

---

## 5. Out of scope

- No scheduler / xv6 / orchestrator / metrics changes.
- No new LLM calls; everything proposed in §4 uses fields the pipeline
  already publishes.
- Runtime correction remains Partial / Future Work.
