# Final Dashboard — Manual QA Checklist

Read-only walk through `dashboard_live` against the demo flow. Pair
this with `docs/final_release_candidate_report.md` (the automated
checks) for the full RC sign-off.

> Run order:
> 1. `python3 scripts/final_demo_check.py`
> 2. `cd dashboard_live && npm run dev` → open
>    `http://localhost:5174`

---

## A. Header strip (first impression, ~15 seconds)

- [ ] **Backend badge** reads **`Backend: XV6 TRACE`** (purple).
      `SIMULATOR FALLBACK` and `FALLBACK` are the simulator and
      demo-fallback states; not expected on a healthy demo.
- [ ] **Manifest meta** shows `workload`, `llm`, `algos`, `seed`,
      `events`.
- [ ] **Snapshot selector** is visible (snapshots are committed on
      main). Starts on `Default (current run)`.
- [ ] **Algorithm dropdown** lists `RR / FCFS / Priority / MLFQ /
      SJF / SRTF`.
- [ ] **Replay / Live toggle** + tick slider visible.

## B. DemoGuide card (top-left, first child of left column)

- [ ] Card label reads **`Demo flow`**.
- [ ] 5 numbered chips visible: `1` Backend badge,
      `2` LLM pick, `3` Metric trade-off, `4` xv6 schedule,
      `5` Generality.
- [ ] Step text fits in the card (no clipping at the row).
- [ ] **Click test (P0-2 spec):**
  - Click `1` → backend badge flashes purple outline ~1.4 s.
  - Click `2` → `LLM Recommendation` card flashes.
  - Click `3` → `Metric trade-off` card flashes.
  - Click `4` → `Main Gantt` card flashes.
  - Click `5` → Snapshot selector flashes (or graceful no-op
    if the selector is hidden — should be visible since
    snapshots ship on main).

## C. LLM Recommendation + Algorithm Guard (left column)

- [ ] **`LLM Recommendation`** shows the recommended algorithm
      pill (e.g. `MLFQ`), target metric pill, params line, and a
      reason paragraph clipped at 3 lines.
- [ ] **`Algorithm Guard`** shows the verdict pill (`ACCEPTED`
      green), the one-line reason, and 3 check chips.

## D. Why this algorithm? (`RecommendationEvidence`)

- [ ] Card label reads `Why this algorithm?`.
- [ ] Top row: workload → algorithm → target metric (+ confidence
      pill if present).
- [ ] Trait chips: `interactive`, `avg burst`, `avg prio`.
- [ ] Scrollable LLM-reason box visible (full reason readable).
- [ ] Guard verdict pill + compat/confidence scores.
- [ ] Provenance pill reads **`LLM: solar-pro3`** (not
      `demo fallback (no LLM call)`).
- [ ] Bottom: judgment pill + regret.

## E. Metric trade-off (`CounterfactualMetricView`)

- [ ] Card label reads `Metric trade-off`.
- [ ] 5 rows: `Response time` (target — purple left-border accent
      and a `target` pill), `Waiting time`, `Turnaround time`,
      `Max waiting`, `Throughput`.
- [ ] Per row: best algorithm + colored dot, value (3-dp for
      throughput, 2-dp otherwise), `vs LLM` cell.
- [ ] Footer line: `LLM-selected <algo> wins N/M metric goals on
      this workload.`
- [ ] **Cross-check with `docs/algorithm_decision_diversity_audit.md`
      §2**: best-per-metric matches the audit table for the
      currently-selected snapshot.

## F. Runtime monitor (`RuntimeCorrectionPreview`)

- [ ] Card label reads `Runtime correction (preview)`.
- [ ] On a healthy run (no events): green dot +
      **`Runtime monitor: no correction needed`** strip, with the
      warning banner **`Preview only — not applied to xv6.`**.
- [ ] No `Detected` / `Proposed` / `Guard verdict` sections when
      events are empty.
- [ ] When events exist (force locally via
      `scripts/correction_preview_smoke.py`'s scenarios or by
      tweaking `event_detector` thresholds — **do not commit**),
      the card renders all three sections and still shows
      "Preview only — not applied to xv6".

## G. Center column (xv6 trace surface)

- [ ] `MainGantt` renders a Gantt for the selected algorithm.
- [ ] `ProcessState` shows the process state table for the
      current tick.
- [ ] `TraceStack` shows the event log.
- [ ] Switching the algorithm dropdown updates all three.

## H. Right column

- [ ] `WorkloadSummary` shows the analyzer's traits.
- [ ] `AlgorithmComparison` shows one row per algorithm; the
      `Judge` cell re-derives when the metric dropdown changes.
- [ ] `MetricVisualization` chart matches the Comparison's
      selected metric.

## I. Snapshot tour (proof of generality)

For each of `interactive`, `cpu_bound`, `mixed`,
`priority_sensitive`:

- [ ] Selector switches; purple `SNAPSHOT: <profile>` pill
      appears.
- [ ] Backend badge stays `XV6 TRACE` — snapshots are real xv6.
- [ ] All cards re-render with the snapshot's data.
- [ ] LLM Recommendation card updates (currently MLFQ on every
      snapshot — see audit §2 for why).

## J. Honesty signs (must not be on screen)

These would be **demo-blocking** if any of them appear on stage:

- [ ] No card claims a correction was applied to xv6.
- [ ] No `CORRECTION_APPLIED` event in the trace stack.
- [ ] No "live correction enabled" / "runtime correction complete"
      copy.
- [ ] No banner suggesting the LLM modified the scheduler
      mid-run.

If any J row is checked, the demo is RED — fix or stop the
presentation.

---

## Known issue from the RC report

`docs/final_release_candidate_report.md` §6 documents the
`interactive` snapshot's RR row anomaly (`avg_response_time = 34.2
ticks` — wildly inconsistent with other algos on the same
workload). This shows up in `AlgorithmComparison` and
`CounterfactualMetricView` when the snapshot selector is set to
`interactive`. Treatment is the P1 PR in the current goal;
amend the RC report to GREEN once that lands. Until then this
QA row stays YELLOW:

- [ ] (Interactive snapshot) RR.avg_response_time is **plausible**
      (within a few ticks of MLFQ / similar workloads).
