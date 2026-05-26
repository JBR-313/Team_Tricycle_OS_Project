# dashboard_live Step Layout — Manual QA

Read-only walk-through verifying the Recommend / Execute / Evaluate
migration shipped in PR #68. Pair with
`docs/final_dashboard_manual_qa.md` (per-card checks) — this doc is
specifically about the step layout.

> Run order:
> 1. `python3 scripts/final_demo_check.py`
> 2. `cd dashboard_live && npm run dev`
> 3. Open `http://localhost:5174` (or `http://<wsl-ip>:5174` on WSL2)

---

## A. Header persistence (must be identical on every step)

For each step (Recommend / Execute / Evaluate), confirm:

- [ ] **Backend badge** reads `Backend: XV6 TRACE` (or
      `SIMULATOR FALLBACK` / `FALLBACK` if the orchestrator
      explicitly fell back).
- [ ] **Manifest meta** (workload / llm / algos / seed / events)
      visible.
- [ ] **Snapshot selector** present (assuming snapshots are
      committed on main).
- [ ] **Algorithm dropdown** present.
- [ ] **Replay / Live toggle + tick slider** present (Live
      polling pauses while a snapshot is selected — same as
      before).
- [ ] **Step pill buttons** `1 Recommend`, `2 Execute`,
      `3 Evaluate` visible between Brand and right controls.
      Active step pill is purple-highlighted.
- [ ] Clicking a step pill switches the screen without
      reloading the page.

## B. DemoGuide persistence

- [ ] DemoGuide card visible at the top of the body, **on every
      step** (not only Recommend).
- [ ] Clicking step `1`–`5` chips still flashes the matching
      element on screen (works cross-step — e.g. clicking
      chip `4` "xv6 schedule" while on Recommend should still
      flash MainGantt **after** navigating to Execute? — note:
      the chip flashes whichever DOM element matches the
      selector. If the matched card is in a different screen,
      the flash will fire after step switch only if the DOM
      element is currently mounted. Treat this as a known
      limitation: navigate to the step before clicking).

## C. Recommend screen

- [ ] Top banner: `Workload Summary` full width.
- [ ] Left column: `LLM Recommendation` + `Why this algorithm?`
      (RecommendationEvidence).
- [ ] Right column: `Algorithm Guard` + `Metric trade-off`
      (CounterfactualMetricView).
- [ ] Provenance pill in evidence card reads
      `LLM: solar-pro3` (or `demo fallback (no LLM call)` —
      should NOT be present on the on-stage demo).
- [ ] Metric trade-off `target` row is highlighted (purple
      left-border + `target` pill).
- [ ] Footer line: `LLM-selected <algo> wins N/M metric goals
      on this workload.`

## D. Execute screen

- [ ] `MainGantt` is the dominant card (top 2fr).
- [ ] Bottom 3-column strip: `ProcessState`, `ProcessLanes`,
      `RuntimeCorrectionPreview`.
- [ ] `TraceStack` capped to ~30% of remaining height, scrolls
      vertically if events overflow.
- [ ] RuntimeCorrectionPreview:
  - Healthy run: shows the "no correction needed" strip + the
    warning banner `Preview only — not applied to xv6.`
  - Card hides itself entirely if `runtime_events.json` is
    absent.

## E. Evaluate screen

- [ ] Top row: `Evaluation Result` (verdict pill + regret + Δ vs
      best) on the left, `LLM Explanation` on the right.
- [ ] Bottom row: `Metric Visualization` (left) + `Algorithm
      Comparison` (right) **side by side**.
- [ ] **Cross-link still works:** flipping the metric dropdown
      in `MetricVisualization` re-derives the `Judge` column in
      `AlgorithmComparison` immediately.

## F. Snapshot tour (proof of generality)

For each of `interactive`, `cpu_bound`, `mixed`,
`priority_sensitive`:

- [ ] Selector switches; purple `SNAPSHOT: <profile>` pill
      appears in the Header.
- [ ] Backend badge stays `XV6 TRACE`.
- [ ] Each step's cards re-render with the snapshot's data.
- [ ] Live polling stays paused while a snapshot is active
      (same behaviour as before the step migration).

## G. Clipping / overflow

- [ ] On a 1080p / 16:9 viewport the 3 screens each fit without
      vertical scroll inside the shell.
- [ ] On narrower windows (e.g. 1366×768), the screens still
      respect the 16:9 shell (no card pushed outside).
- [ ] Long LLM-reason text inside the Evidence card scrolls
      inside the card, not the parent column.
- [ ] LLM Explanation in Evaluate's top-right does not push
      EvaluationResult off-screen.

## H. Honesty (must NOT appear)

- [ ] No card claims a correction was applied to xv6.
- [ ] No `CORRECTION_APPLIED` event in the trace stack.
- [ ] No "live correction enabled" copy.
- [ ] No banner suggesting the LLM modified the scheduler
      mid-run.

If any **H** row is checked, the demo is RED — fix or stop the
presentation.

---

## Known sub-perfections (acceptable on stage)

- DemoGuide's click-to-flash on a chip whose target lives on a
  different step will only flash after navigating to that step
  (the matching DOM element must be currently mounted).
- The bottom 30% TraceStack cap means very long traces clip
  in Execute. Drag scrollbar inside `TraceStack` to inspect.

## Verdict

Each of A–H must be ✅ for the migration to be considered
ready. If any row is ❌, file as a follow-up bug; do not block
the demo on cosmetic concerns unless they're in H (honesty).
