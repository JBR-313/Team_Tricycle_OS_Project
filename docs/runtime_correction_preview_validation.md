# Runtime Correction Preview — Validation Plan

Schema and honesty rules for the three preview artifacts published
by `scripts/orchestrator.py:_run_correction_preview`. This plan is
the spec for the follow-up validator extension (P0-2) and the CI
coverage (P0-3). It does **not** change the strict dashboard
contract — preview files remain optional and off-contract by
design.

> Read alongside `docs/runtime_correction_preview_design.md` (the
> design spec) and
> `docs/runtime_correction_preview_demo_gap.md` (the demo
> visibility story).

---

## 1. Files in scope

Located under `dashboard_live/public/live-data/`. All three are
**optional**:

| File | Producer | When written |
|------|----------|--------------|
| `runtime_events.json` | `tools/event_detector.py` | always, when the orchestrator runs the preview step |
| `correction_proposal.json` | `tools/correction_proposer.py` | only when `runtime_events.events` is non-empty |
| `correction_guard_decision.json` | `tools/correction_guard.py` | only when a proposal exists |

A clean healthy demo produces only `runtime_events.json` with
`events: []`. That is the legitimate quiet state.

## 2. Honesty invariants (must hold on every produced file)

These are non-negotiable. The validator refuses anything that
breaks them, regardless of other shape issues.

| Invariant | Applies to | Why |
|-----------|------------|-----|
| `preview_only === true` at top-level | `correction_proposal.json`, `correction_guard_decision.json` | The whole preview surface promises no live-apply. Anything missing the flag is treated as a forged "live" artifact. |
| `applied === false` at top-level | same | Mirrors the design's `applied=false` rule. The proposer never sets `applied=true`; the guard refuses to validate anything that does. |
| **no `CORRECTION_APPLIED` field** anywhere in either file | same | The dashboard reserves this trace event for the (future) closed-loop apply. The preview must never claim it. |
| `runtime_events.json` has the shape `{ total_problems: int, events: array }` and never carries `applied=true` | `runtime_events.json` | Event detection is observational; nothing was applied. |

## 3. Per-file schema

### 3.1 `runtime_events.json`

```jsonc
{
  "total_problems": <int >= 0>,
  "events": [
    {
      "tick": <int>,
      "type": "starvation" | "high_response_time" |
              "high_preemption_rate" | "low_throughput",
      "pid": <int | -1>,
      "detail": <string>,
      "severity": "low" | "medium" | "high"
    },
    ...
  ]
}
```

Validator checks:

- File exists and parses as JSON.
- `total_problems` is a non-negative int and equals `len(events)`.
- Each event has `type` ∈ the listed set, `severity` ∈
  {`low`, `medium`, `high`}, `tick` ∈ int, `pid` ∈ int.
- No top-level `applied` field with value `true`.

### 3.2 `correction_proposal.json` (optional)

```jsonc
{
  "preview_only": true,
  "applied": false,
  "current_scheduling_algorithm": <string>,
  "triggered_by": [ <runtime_event>, ... ],
  "proposed": {
    "correction_type": "aging_strengthen" | "quantum_decrease"
                     | "quantum_increase" | "parameter_update"
                     | "algorithm_change" | "no_op",
    "new_scheduling_algorithm": <string>,
    "new_params": { ... },
    "rationale": <string>,
    "triggering_event": <runtime_event>
  },
  "_meta": { "source": <string>, "generated_at": <ISO-8601>,
             "rule_version": <int> }
}
```

Validator checks:

- File must exist iff `runtime_events.events` is non-empty.
  - Events empty + proposal present → WARN (orphan proposal).
  - Events non-empty + proposal absent → WARN (preview broke).
- `preview_only === true` AND `applied === false`. Any
  violation → ERROR.
- `proposed.correction_type` ∈ the listed set.
- `proposed.new_scheduling_algorithm` is a non-empty string.
- `proposed.new_params` is an object (may be empty for FCFS).
- `proposed.triggering_event` is present and matches an entry
  in `runtime_events.events` by `tick` + `type` (cross-check).

### 3.3 `correction_guard_decision.json` (optional)

```jsonc
{
  "preview_only": true,
  "applied": false,
  "guard_result": "accepted" | "rejected",
  "proposal_source": "correction_proposal.json",
  "correction_type": <string>,
  "new_scheduling_algorithm": <string>,
  "reason": <string>,
  "rejected_params": [ <string>, ... ],   // present only on rejection
  "fallback": { ... },                    // present only on rejection
  "_meta": { ... }
}
```

Validator checks:

- File must exist iff `correction_proposal.json` exists.
  - Proposal present + decision absent → ERROR (orphan
    proposal without a guard verdict).
  - Decision present + proposal absent → WARN (orphan
    decision).
- `preview_only === true` AND `applied === false`. Any
  violation → ERROR.
- `guard_result` ∈ {`accepted`, `rejected`}.
- On `rejected`: `rejected_params` is a non-empty array and
  `fallback.correction_type` is `no_op`.

## 4. Validator behavior

A new optional flag, `--preview`, opted in explicitly:

```bash
python3 tools/validate_dashboard_contract.py --strict \
    --dir dashboard_live/public/live-data \
    --snapshots dashboard_live/public/live-data/snapshots \
    --preview
```

Rules:

- **Default mode** (no `--preview`): behaviour unchanged. Preview
  files are neither required nor validated. `final_demo_check.py`
  keeps passing on a healthy run that emits only an empty
  `runtime_events.json`.
- **`--preview` mode**:
  - If none of the three files exist, the preview is reported as
    `[OK] preview not present`. (The orchestrator may not have
    run yet, or the dashboard root is a snapshot without
    preview.)
  - Otherwise, each present file is checked per §3.
  - All honesty invariants (§2) are ERRORs in `--strict --preview`
    mode regardless of the rest. The validator never accepts a
    forged "live" preview artifact.

## 5. CI plan (P0-3)

The lightweight CI in `.github/workflows/ci.yml` already runs:

1. `py_compile tools/*.py scripts/*.py`
2. `tools/validate_dashboard_contract.py --strict` (no
   `--preview`)
3. `npm run build` for both dashboards.

Add to the `python` job:

4. `python3 scripts/correction_preview_smoke.py` — exercises the
   proposer + guard rule table on synthetic events without
   touching live-data. Already exits 0 on success per PR #56.
5. `python3 tools/validate_dashboard_contract.py --strict
   --preview --dir dashboard_live/public/live-data` — opt-in
   preview validation against the committed live-data root.
   The committed live-data does **not** include preview files
   by design (we don't ship a possibly-stale preview), so the
   validator will report "preview not present" and exit clean.

QEMU is **not** added to CI; the local
`scripts/final_demo_check.py` remains authoritative for the
xv6 path.

## 6. Out of scope

- No xv6 kernel change.
- No `CORRECTION_APPLIED` trace event emission.
- No change to the existing strict contract (preview files
  remain off-contract by design).
- No new LLM call, no fake events, no live-data mutation.
- No closed-loop apply (still Future Work — see
  `docs/runtime_correction_preview_design.md` §7).

## 7. Sequencing of follow-up PRs

1. **P0-2** — extend `tools/validate_dashboard_contract.py`
   with the `--preview` flag implementing §3 + §4. Default
   behaviour unchanged.
2. **P0-3** — add the new steps from §5 to
   `.github/workflows/ci.yml`'s `python` job.
3. **P1** — short cross-link in README or defense notes if
   needed (likely only a single bullet pointing at this doc).

Each PR keeps `final_demo_check.py` passing.
