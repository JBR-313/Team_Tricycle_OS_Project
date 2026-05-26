# dashboard_live — Step Layout Migration Plan

Migrate `dashboard_live` from the dense 3-column observability
layout to the Recommend / Execute / Evaluate step-based screen
pattern that `dashboard_test` already uses. Keep every live-data
feature intact. No data-contract or scheduler change.

> Companion: `docs/dashboard_live_demo_readability_audit.md` (which
> first identified the entry-point problem and recommended DemoGuide)
> and `docs/runtime_correction_preview_design.md` (which keeps
> dictating where the preview card lives).

---

## 1. Current `dashboard_live` layout

`App.jsx` renders a header bar + a 3-column `dashboard-main`:

| Column | Cards (top → bottom) |
|--------|----------------------|
| Left   | `DemoGuide`, `LLMRecommendation`, `AlgorithmGuard`, `RecommendationEvidence`, `CounterfactualMetricView`, `RuntimeCorrectionPreview`, `EvaluationResult`, `LLMExplanation` |
| Center | `MainGantt`, `ProcessState`, `TraceStack` |
| Right  | `ProcessLanes`, `WorkloadSummary`, `AlgorithmComparison`, `MetricVisualization` |

14 cards on one screen. The readability audit (PR #45) already
called this out: no labeled entry point; cards bunched. The
DemoGuide card (PR #46/#47) helps but doesn't change the
information density.

## 2. `dashboard_test` step pattern (reference)

`dashboard_test/src/App.jsx` (already shipped) uses three
conditionally-rendered screens driven by a `step` state:

```jsx
{step === 'Recommend' && <div className="screen-recommend">…</div>}
{step === 'Execute'   && <div className="screen-execute">…</div>}
{step === 'Evaluate'  && <div className="screen-evaluate">…</div>}
```

The header shows three pill-shaped buttons (`1 Recommend`,
`2 Execute`, `3 Evaluate`) that toggle the screen. Each screen
arranges only the relevant cards.

## 3. Live mapping (cards → screens)

Reuse existing live components — no new components, no new
features.

### Recommend (the "before" story)

| Card | Source |
|------|--------|
| `WorkloadSummary` | existing |
| `LLMRecommendation` | existing |
| `AlgorithmGuard` | existing |
| `RecommendationEvidence` | existing |
| `CounterfactualMetricView` | existing |

Layout intent: workload at top (full-width banner), LLM
recommendation dominant on the left, Guard + Evidence + Trade-
off on the right.

### Execute (the "running" story)

| Card | Source |
|------|--------|
| `MainGantt` | existing — dominant |
| `ProcessState` | existing |
| `ProcessLanes` | existing |
| `TraceStack` | existing — keep below the fold / collapsible |
| `RuntimeCorrectionPreview` | existing — small strip in this screen |

Layout intent: Gantt dominant, smaller cards in a bottom strip.

### Evaluate (the "after" story)

| Card | Source |
|------|--------|
| `EvaluationResult` | existing |
| `MetricVisualization` | existing |
| `AlgorithmComparison` | existing |
| `LLMExplanation` | existing |

Layout intent: verdict on top, then `MetricVisualization` (left)
and `AlgorithmComparison` (right) side by side. The
`MetricVisualization.selectedMetric` ↔ `AlgorithmComparison` link
must continue to work — both already read from the same App-level
state.

### Persistent (across all 3 screens)

- The **DemoGuide** card. Stays visible in a small sidebar / top
  strip so the presenter can flash any card from any step. (Or
  fold its 5 steps into the step-navigation buttons themselves
  — see §6 trade-off.)
- The **Header** bar with every existing live element: backend
  badge, snapshot selector, snapshot pill, manifest meta,
  algorithm dropdown, replay/live toggle, tick slider, data
  status, fallback banner.

## 4. What must NOT be ported from `dashboard_test`

These exist in the UI-lab and would break the live experience:

- **Fixture data system** (`dashboard_test/src/data/fixtures.js`,
  preset selectors). `dashboard_live` already has
  `liveDataClient.js` + snapshot selector — the source of truth.
- **`UITestControls`** (`dashboard_test/src/components/UITestControls.jsx`):
  dev-only debug overlay for cycling fixture states. No place in
  the live demo.
- **Preset / focus controls** inside `dashboard_test/App.jsx` for
  switching the simulated workload. The live equivalent is the
  snapshot selector in the live Header.
- **`ExecuteInfoCard`** unless we judge it adds presenter value
  on real xv6 traces. For the initial migration we will NOT port
  it; revisit only if an objective gap is found during QA.
- **Streamlit / legacy theme styles** if any have leaked.

## 5. Header changes (live, careful)

Add three step buttons to `Header.jsx`. The live Header is
*much* larger than the test Header (it also carries backend
badge, snapshot selector, manifest meta, fallback banner, …),
so the step buttons need to fit without pushing the existing
controls off-screen.

Strategy:

1. Add `step` + `onStepChange` props to `Header.jsx`.
2. Insert the three step buttons between `Brand` and the
   first existing `header-spacer`. The existing layout flows
   right; the steps become the first thing the eye sees after
   the brand.
3. Keep `backend-badge`, `header-data-status`,
   `header-manifest-meta`, `Algorithm` dropdown, `Snapshot`
   dropdown, replay/live toggle, tick slider EXACTLY as today.
   None of them are about step navigation; all must remain.

If the header gets too wide on a 14-inch screen, fall back to
wrapping (`flex-wrap: wrap`) inside the existing
`.header-bar`.

## 6. DemoGuide trade-off

Two options, decide during P0-3:

| Option | Trade-off |
|--------|-----------|
| A. Keep `DemoGuide` as a small persistent card top-left of every screen. | Cheap; preserves click-to-flash for every step. May feel redundant once step nav exists. |
| B. Replace DemoGuide chips with `Header.jsx` step buttons; keep the click-to-flash only on the active step's main card. | Saves vertical space. Removes the "5 distinct flashes" demonstration ability, but step buttons themselves now lead the eye. |

Recommended: **A** for the first migration PR (zero behavioural
risk). Revisit B as polish after QA if redundancy is obvious.

## 7. CSS porting plan

From `dashboard_test/src/App.css`, port only these layout
class blocks (and adapt to `dashboard_live`'s background/theme):

- `.screen-recommend`
- `.screen-recommend .rec-top`, `.rec-left`, `.rec-right`
- `.screen-execute`
- `.screen-execute .exec-gantt`, `.exec-bottom`, `.exec-debug*`
- `.screen-evaluate`
- `.screen-evaluate .eval-top`, `.eval-bottom`
- `.header-steps`, `.header-step-btn`, `.step-num`

Do **not** port:

- `dashboard_test`'s fixture-driven preset styles.
- `dashboard_test`'s lighter / heavier theme variants. The live
  background colour and brand colour stay the current live
  values.

## 8. Sequencing of follow-up PRs

1. **P0-2** — minimal Header change: add `step` state in `App.jsx`,
   add `step` / `onStepChange` props to `Header.jsx`, render
   three step buttons. Keep the 3-column body for now (so the
   buttons are inert visually until P0-3 wires them).
2. **P0-3** — replace the always-visible 3-column
   `dashboard-main` with three conditionally-rendered
   `screen-*` blocks per §3. Reuse every card. Keep snapshot
   selector + live polling unchanged.
3. **P0-4** — port the layout CSS classes per §7. No theme
   change.
4. **P1** — `docs/dashboard_live_step_layout_qa.md`: manual QA
   checklist for each step + persistent header + RuntimeCorrection
   healthy state + snapshot tour + metric-dropdown sync between
   `MetricVisualization` and `AlgorithmComparison`.

Each PR keeps `final_demo_check.py` passing because no data /
scheduler / contract changes happen at any step.

## 9. Out of scope (this migration goal)

- No scheduler, xv6, orchestrator, validator, metrics, or
  data-contract changes.
- No closed-loop runtime correction.
- No new dashboard cards.
- No theme / color redesign.
- No fixture system / UITestControls porting.
