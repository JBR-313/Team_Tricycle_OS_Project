# Runtime Correction Preview — Demo Visibility Gap

The runtime correction preview pipeline (PRs #51 → #54) ships end-to-end,
but the **healthy on-stage demo** of `final_demo_check.py` produces zero
runtime events, so the `RuntimeCorrectionPreview` card hides itself.
That's the correct technical behaviour — there is nothing to correct —
but it leaves a presenter on stage with no way to show that the
preview pipeline exists at all.

This audit names the gap, the **honest** demo paths to close it, and
the items that stay Future Work.

> Companion to `docs/runtime_correction_preview_design.md` (the
> design spec) and `docs/implementation_status.md` (the canonical
> status table).

---

## 1. Why the healthy run shows nothing

`scripts/orchestrator.py:_run_correction_preview` runs
`event_detector.py` against the **fresh** xv6 trace and metrics for
the LLM-selected algorithm. The detector thresholds are:

| Threshold (in `tools/event_detector.py`) | Default |
|------------------------------------------|---------|
| `STARVATION_THRESHOLD` (ticks without CPU) | 40 |
| `THRUPUT_THRESHOLD` (procs/tick)           | 0.05 |
| `PREEMPT_THRESHOLD` (preempts/tick)        | 0.30 |
| `RESPONSE_THRESHOLD` (avg response, ticks) | 10 |

On the curated xv6 demo workload (`interactive`, `--seed 42`, 4–5
children, makespan ≈ 16 ticks) MLFQ + the LLM's recommended params
produce:

- max wait ≈ 1 tick (well under STARVATION_THRESHOLD=40)
- avg response ≈ 0.0 (well under RESPONSE_THRESHOLD=10)
- throughput ≈ 0.3 (well over THRUPUT_THRESHOLD=0.05)
- preempt rate ≈ 0.25 (just under PREEMPT_THRESHOLD=0.30)

So `runtime_events.events` is **legitimately empty**. The dashboard
card hiding itself is correct: there is nothing to propose.

> **Important:** the project rules forbid faking diversity. We do
> **not** lower the detector thresholds just to make the card
> render on the demo workload — that would be dishonest.

## 2. Two honest demo paths

### Path A — show the healthy state itself (this goal's P0-2)

Today the card returns `null` when events are empty. Switch that
to a **compact monitor strip**: when `runtime_events.json` exists
with `events.length === 0`, render a one-liner like

> `Runtime monitor: no correction needed` *(Preview only — not
> applied to xv6.)*

That makes the preview **visible** on the healthy demo without
fabricating events. The audience sees the system is watching;
the absence of a proposal is the honest answer.

### Path B — synthetic smoke from the terminal (this goal's P0-3)

Add `scripts/correction_preview_smoke.py`. The script:

1. Builds an **in-memory** `runtime_events` payload listing each
   detector event type with a real-looking severity.
2. Calls `tools/correction_proposer.py` and
   `tools/correction_guard.py` on **temporary files** in
   `/tmp` (or a passed `--out-dir`).
3. Prints a compact summary showing the rule fired and whether
   the Guard accepted or rejected.
4. **Never touches** `dashboard_live/public/live-data/`. Cannot
   contaminate the on-stage demo data.

The script lets a presenter demonstrate the proposer + guard
deterministically (e.g. "this is what the system would have
proposed if starvation HAD been detected"), without claiming the
correction was applied.

## 3. What stays Future Work

Closing the loop to a real applied correction inside a running
xv6 guest still requires (unchanged from the design doc §7):

1. **Kernel** — system calls in `xv6-riscv/kernel/proc.c` to
   change the algorithm and parameters mid-run.
2. **schedtest.c** — accept a follow-up directive (likely via a
   serial-console marker or pseudo-pipe) and re-call
   `setscheduler()` with new params.
3. **Orchestrator** — pipe the guard-accepted proposal back into
   the running QEMU instance and observe the apply ack.
4. **Trace parser** — recognise a new `CORRECTION_APPLIED` event
   and surface it distinctly in the dashboard timeline.

None of this is in scope for the current goal. The preview is
documented in `docs/runtime_correction_preview_design.md` §7 as
the next step toward, not the closure of, that loop.

## 4. What this audit does NOT change

- No xv6 kernel changes.
- No detector threshold tuning (no faked diversity).
- No `CORRECTION_APPLIED` trace event emission.
- No mutation of `dashboard_live/public/live-data/`.
- No claim that any correction was applied to xv6.
- README §12.1 row stays `Runtime correction loop … Partial /
  Future Work`. Every new artifact still says
  `preview_only=true, applied=false`.

## 5. Sequencing of follow-up PRs

1. **P0-2** — small change in
   `dashboard_live/src/components/RuntimeCorrectionPreview.jsx`
   to render the "no correction needed" monitor state when
   `runtime_events.events.length === 0`. Hiding behaviour preserved
   for the case where `runtime_events.json` itself is absent.
2. **P0-3** — new `scripts/correction_preview_smoke.py`. Reads
   the proposer/guard via subprocess on synthetic events in a
   temp dir. Read-only with respect to live-data.
3. **P1** — short cross-link entries in
   `docs/presenter_script.md` and
   `docs/presentation_defense_notes.md` describing how to use the
   monitor strip + the smoke script during the demo.

All three PRs must keep `final_demo_check.py` passing and must
not change the strict contract; preview files remain off-contract
by design.
