# Runtime Correction Preview — Design

This is the design spec for a **preview-only** runtime-correction
loop. It surfaces detected scheduling problems and a guard-validated
correction proposal on screen, but it does **not** apply the
correction to xv6. No xv6 kernel code is touched.

This is the next honest step beyond `tools/event_detector.py`. The
full closed-loop `CORRECTION_APPLIED` story remains Future Work and
is explicitly out of scope here.

> Status everywhere it appears: `preview_only=true`, `applied=false`.
> The README §12.1 row stays
> "Runtime correction loop … Partial / Future Work" because we are
> shipping a **preview**, not the apply step.

---

## 1. Why a preview, not an apply

Applying a mid-run correction requires three things this repo does
not have:

- A back-channel from the host orchestrator into a running xv6 guest
  (today, each algorithm is a fresh QEMU boot — no live channel).
- A kernel-side path to change scheduler / params mid-run and emit
  a `CORRECTION_APPLIED` trace event (xv6 kernel currently sets the
  algorithm via `setscheduler()` from `schedtest.c` once, before
  forking; no setter for params during a run).
- A re-validation hook that re-runs the Guard on the correction
  and writes the decision into the trace.

A preview surfaces the **same information** an audience would see
if the loop were closed — "the system noticed X, and would propose
Y, and the Guard would accept/reject it" — without making any of
the kernel changes above. It is honest about not applying, and it
unblocks the demo story.

## 2. Inputs

All inputs already exist on every run:

| File | Source | Purpose in the preview |
|------|--------|------------------------|
| `dashboard_live/public/live-data/metrics.json` | orchestrator | top-level scalars (avg_response_time, throughput, preemption_count, starvation_occurred, etc.) drive metrics-based proposals |
| `dashboard_live/public/live-data/trace_<algo>.jsonl` | orchestrator | trace events feed `tools/event_detector.py` (already exists) |
| `dashboard_live/public/live-data/recommendation.json` | LLM Advisor | the algorithm + params the LLM picked; proposals can adjust this rather than the per-algorithm comparison row |
| `dashboard_live/public/live-data/guard_decision.json` | Algorithm Guard | the original guard decision; the new Correction Guard re-checks the proposal against the same range rules |

## 3. New outputs

Two new files, written into the same flat live-data root so the
dashboard reads them with the existing base swap. Both are optional
— absent when no events were detected.

### 3.1 `runtime_events.json` (already-shipped shape, optional today)

`tools/event_detector.py` already emits this file. The preview
loop ensures the orchestrator writes it. Schema (unchanged):

```jsonc
{
  "total_problems": <int>,
  "events": [
    { "tick": <int>, "type": "starvation"
                          | "high_response_time"
                          | "low_throughput"
                          | "high_preemption_rate",
      "pid": <int|-1>, "detail": "...", "severity": "low"|"medium"|"high" },
    ...
  ]
}
```

### 3.2 `correction_proposal.json` (new — P0-2 ships this)

Written by the new `tools/correction_proposer.py`. **Deterministic
rules first** — no LLM call. Schema:

```jsonc
{
  "preview_only": true,
  "applied": false,
  "current_scheduling_algorithm": "MLFQ",          // from recommendation.json
  "triggered_by": [
    { "type": "starvation", "tick": 32, "pid": 5, ... }   // copied from runtime_events
  ],
  "proposed": {
    "correction_type": "parameter_update"|"algorithm_change"
                      |"aging_strengthen"|"quantum_increase"
                      |"quantum_decrease",
    "new_scheduling_algorithm": "MLFQ",            // unchanged unless algorithm_change
    "new_params": { "quantum": [2,4,8], "aging_threshold": 20, ... },
    "rationale": "starvation detected -> aging_threshold halved"
  },
  "_meta": {
    "source": "tools/correction_proposer.py",
    "generated_at": "ISO-8601 UTC",
    "rule_version": 1
  }
}
```

Mapping from event type to proposal (the deterministic rule
table):

| Event type            | Proposal                                                    |
|-----------------------|-------------------------------------------------------------|
| `starvation`          | `aging_strengthen` — halve `aging_threshold` (floor at 5)   |
| `high_response_time`  | `quantum_decrease` — halve top-queue quantum (floor at 2). If current algo is FCFS, propose `algorithm_change` to RR. |
| `high_preemption_rate`| `quantum_increase` — double top-queue quantum (cap at 100)  |
| `low_throughput`      | `parameter_update` — reduce excessive preemption: increase top-queue quantum AND raise `boost_interval` 1.5× |

Multiple events ⇒ one proposal per **highest-severity** event
(starvation > medium > low). The other events are still listed
under `triggered_by` so the audience sees them.

If `runtime_events.events` is empty, the proposer writes
**no file** (and the dashboard hides the card).

### 3.3 `correction_guard_decision.json` (new — P0-3 ships this)

Written by the new `tools/correction_guard.py`. Re-uses the existing
Guard range-check logic against the **proposed** params. Schema:

```jsonc
{
  "preview_only": true,
  "applied": false,
  "guard_result": "accepted" | "rejected",
  "proposal_source": "correction_proposal.json",
  "reason": "...",
  "rejected_params": ["aging_threshold"],   // present only if rejected
  "fallback": {                              // present only if rejected
    "correction_type": "no_op",
    "rationale": "preview retained the original recommendation"
  },
  "_meta": {
    "source": "tools/correction_guard.py",
    "generated_at": "ISO-8601 UTC"
  }
}
```

## 4. Pipeline placement

`scripts/orchestrator.py`'s end-of-run sequence becomes:

```
... (existing) ...
[4] backend run → trace_<algo>.jsonl per algo
[5] aggregate metrics.json
[6] strict-validate dashboard contract     # existing
[7] (NEW, optional preview)
    a. tools/event_detector.py → runtime_events.json
    b. if events non-empty:
         tools/correction_proposer.py → correction_proposal.json
         tools/correction_guard.py    → correction_guard_decision.json
    c. publish (a)/(b) into dashboard_live/public/live-data/
```

Step 7 is **non-blocking**: a missing or empty
`runtime_events.events` list is OK; the orchestrator continues
and the dashboard simply omits the preview card. Validation step
[6] is still strict; the preview files are not added to the
contract schema in this goal — they live alongside it.

## 5. Dashboard surface (P1)

One new card, **`RuntimeCorrectionPreview`**, in the existing
left column right after `RecommendationEvidence`. Shows:

- `Preview only — not applied to xv6` banner (warning-tint pill).
- Up to three detected problems with severity dots.
- The proposal: correction type, new params or new algo, rationale.
- The Correction Guard verdict: accepted (green) or rejected
  (red, with reason).

If any of the three files is missing the card hides itself
(`return null`). Layout-neutral; no card removed, no card moved.

## 6. Honesty rules

- Every output file carries `preview_only: true` and
  `applied: false` at the top.
- The card always shows "Preview only — not applied to xv6."
- `manifest.json` and `metrics.json` are **not** mutated by the
  preview pipeline. The corrected params never feed back into a
  fresh xv6 run. No `CORRECTION_APPLIED` trace event is
  fabricated.
- `README.md` and `docs/implementation_status.md` stay the same.
  The §12.1 status row stays Partial / Future Work; the new
  preview is a step towards it, not the closure.

## 7. Future Work (out of scope here)

Closing the loop later would require:

1. `xv6-riscv/kernel/proc.c` — add system calls to change
   algorithm / params mid-run.
2. `xv6-riscv/user/schedtest.c` — listen on a host channel (UART
   write to a known agreed marker) or accept a follow-up shell
   command to re-`setscheduler()` with updated params.
3. Orchestrator — pipe the guard-accepted proposal back into
   the running QEMU.
4. `tools/trace_parser.py` / kernel — emit a
   `CORRECTION_APPLIED` event the dashboard can render
   distinctly from the preview.

None of this is in scope for this goal. The preview stops at
"guard says OK".

## 8. Sequencing of follow-up PRs

1. **P0-2** — `tools/correction_proposer.py` (deterministic, no
   LLM call). Unit-testable from a synthetic
   `runtime_events.json` plus a real `metrics.json`.
2. **P0-3** — `tools/correction_guard.py` reusing the existing
   Guard range-check helpers.
3. **P0-4** — orchestrator preview hook (step [7]). Non-blocking.
4. **P1** — `RuntimeCorrectionPreview.jsx` card. Hides when files
   are absent.

Each PR keeps `final_demo_check.py` passing because the strict
validator is unchanged — preview files are not on the contract.

## 9. Out of scope (this PR and the follow-ups)

- No xv6 kernel changes.
- No applied correction during xv6 execution.
- No `CORRECTION_APPLIED` trace event.
- No data-contract expansion in this goal.
- No new LLM call (deterministic rules only).
