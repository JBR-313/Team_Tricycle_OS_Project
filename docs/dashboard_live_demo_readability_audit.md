# dashboard_live — Demo Readability Audit

dashboard_live has grown into a 3-column, 13-card layout. The
features are right, but a first-time audience cannot tell where to
look. This audit maps what's on screen, the order the presenter
should walk through it, and the minimum guidance that helps without
redesigning anything.

> Companion to `docs/demo_checklist.md` (terminal commands),
> `docs/presenter_script.md` (3-minute beat-by-beat),
> `docs/recommendation_evidence_audit.md`,
> `docs/algorithm_decision_diversity_audit.md`,
> `docs/counterfactual_metric_view_plan.md`.

---

## 1. Current layout (as of main `033940f`)

The header bar (`Header.jsx`) carries the backend badge,
manifest meta (workload / llm / algos / seed / events), the
snapshot selector (PR #37), the algorithm dropdown, and the
replay/live + tick controls.

Three columns below:

| Column | Cards (top → bottom) |
|--------|----------------------|
| Left   | `LLMRecommendation`, `AlgorithmGuard`, **`RecommendationEvidence`** (PR #32), **`CounterfactualMetricView`** (PR #43), `EvaluationResult`, `LLMExplanation` |
| Center | `MainGantt`, `ProcessState`, `TraceStack` |
| Right  | `ProcessLanes`, `WorkloadSummary`, `AlgorithmComparison`, `MetricVisualization` |

13 cards plus the header. Roughly 6 of those are "demo-critical";
the rest are real-time inspection surfaces.

## 2. Demo-critical cards (the story spine)

In the order the presenter should hit them on stage:

| # | Card | What it answers |
|---|------|-----------------|
| 1 | Header (backend badge + snapshot pill) | "Is this real xv6? Which workload?" |
| 2 | `LLMRecommendation` | "What did the LLM pick?" |
| 3 | `AlgorithmGuard` | "Did anything stop a bad pick?" |
| 4 | `RecommendationEvidence` | "Why did the LLM pick that?" |
| 5 | `CounterfactualMetricView` | "Would another algorithm win if the goal changed?" |
| 6 | `MainGantt` (or `ProcessLanes`) | "Does the schedule on screen actually match the recommendation?" |
| 7 | `AlgorithmComparison` + `MetricVisualization` | "Across every algorithm on the same workload, what does the data say?" |
| 8 | `EvaluationResult` | "Final SUCCESS / NEAR-SUCCESS / FAIL + regret." |
| 9 | `LLMExplanation` | "Natural-language summary." |

The remaining cards (`WorkloadSummary` in the right column,
`ProcessState`, `TraceStack`) are useful for follow-up questions
but are not part of the spine.

## 3. Where the screen feels dense

Concrete pain points observed in the screenshots / build output
on current `main`, without subjective layout opinion:

- **Three columns × thirteen cards** = the audience eye lands
  somewhere random first. There is no labeled entry point.
- **Two cards labeled "LLM ..."** in the left column
  (`LLMRecommendation` + `LLMExplanation`) sandwich the
  evidence/counterfactual content. A new viewer cannot tell that
  one is _before-run_ recommendation and the other is _after-run_
  explanation without reading the headers.
- **`AlgorithmComparison` Judge column** depends on the metric
  dropdown in `MetricVisualization` right below it. The vertical
  coupling is real but unsignposted.
- **Snapshot selector and Algorithm selector live side-by-side
  in the header.** They control different things; right now they
  are both `<select>` styled identically. Cognitive load.

None of these require a layout redesign. They require **labels
that say where the eye should land in which order**.

## 4. Minimal guidance options (no layout change)

| Option | Surface | Impact |
|--------|---------|--------|
| **A. A compact `DemoGuide` card with 5 numbered steps** | new file in left column (e.g. between Header and `LLMRecommendation`, OR as a small strip-style card at top-of-column 1) | Best signal-to-noise. Audience reads the 5 steps once, then follows the spine. |
| B. Numbered chips on existing cards (e.g. `1` on `LLMRecommendation`, `2` on `RecommendationEvidence`, etc.) | tiny CSS-only edit per card | Less noisy, but distributes the story across 6 files and is harder to keep aligned. |
| C. A `<details>` "How to read this" element in the header | one-line summary expanded on click | Hidden by default; presenter has to remember to open it. |

**Recommend A.** A single small card with 5 steps gives the
audience a labeled entry point on the first second of the demo,
disappears into background by step 6, and survives any future
card additions because it references cards by name, not by
DOM position.

## 5. Spec for the recommended DemoGuide card

Label: **`Demo flow`** (or `How to read this`). 5 numbered steps,
each one sentence. Visible from first paint; never blocks the
existing cards.

```
1. Check backend badge — must read XV6 TRACE.
2. Read the LLM pick (top-left) and the "Why this algorithm?" card.
3. Look at "Metric trade-off" to see who would win on other goals.
4. Open the Gantt (center) to see the real xv6 schedule.
5. Switch the snapshot selector in the header to prove the pipeline
   generalises across all four xv6 profiles.
```

Optional, only if cheap: clicking a step adds a small CSS
highlight (`box-shadow` or `outline`) to the matching card for a
few seconds. Pure presentation; no scroll-into-view (snapshots
fit in one viewport on a 1080p screen).

## 6. What this audit does NOT propose

- No layout redesign (columns + card flow stay as today).
- No card removed or moved.
- No data contract change.
- No scheduler / xv6 / orchestrator change.
- No runtime correction implementation (still Partial / Future
  Work).
- No new LLM calls.

## 7. Sequencing of follow-up PRs

1. **P0-2** — add `DemoGuide.jsx`, wire as the first child of the
   left column. Five static steps; no interactivity. ~1 small
   file + 2 lines in `App.jsx`.
2. **P0-3 (only if it stays small)** — add an optional `data-
   demo-anchor` attribute on the demo-critical cards and a tiny
   click-handler in `DemoGuide` that flashes the matching card's
   border. If the highlight requires touching every target card
   individually, skip P0-3 and stop after P0-2.
3. **P1** — update `docs/demo_checklist.md` and
   `docs/presenter_script.md` so the on-stage docs reference the
   new card instead of listing the cards by hand.

Each PR follows the existing one-PR-one-fix loop and keeps
`final_demo_check.py` passing.
