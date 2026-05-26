# Runtime Correction — Design (Partial / Target Architecture)

> Status: **Simulator loop implemented; xv6 apply is Future Work.**
> detect → propose → guard-validate → **apply (simulator)** → `CORRECTION_APPLIED`
> → dashboard now runs end-to-end for the **simulator backend** (rule-based, no
> LLM required). Still Future Work: LLM-assisted proposals and **xv6 mid-run
> application** (needs a kernel control channel, see §5).

## 1. Current state (honest)

| Step | Component | Exists? |
|------|-----------|---------|
| Detect a scheduling problem from the running trace + metrics | `tools/event_detector.py` → `runtime_events.json` | **Yes** |
| Propose a correction (rule and/or LLM) | `correction_proposer` | No |
| Validate the proposed correction | `tools/algorithm_guard.py` (reuse) | Partial (validates recommendations, not corrections yet) |
| Apply the correction from the next scheduling point | simulator / xv6 backend | **Simulator: yes** (`scheduler_simulator.py --correction`); xv6: No |
| Record `CORRECTION_APPLIED` in the trace | backend tracer | **Simulator: yes** (emitted at `apply_from_tick`); xv6: No |
| Visualize the correction | `dashboard_live` `TraceStack` already renders `CORRECTION_APPLIED` | Yes (render only) |

`event_detector.py` already emits problems shaped like:

```json
{ "type": "starvation", "tick": 80, "pid": 4, "severity": "high", "detail": "..." }
```
(`type` ∈ `starvation | low_throughput | high_preemption_rate | high_response_time`).

## 2. Goals & hard constraints (from CLAUDE.md)

- The **LLM is not the scheduler.** It must NOT be called every timer tick and must
  NOT choose the next process per tick.
- Correction is **event-triggered** (Event Detector), not continuous.
- A correction is **applied from the next scheduling point**, never retroactively.
- Every correction is **validated by Algorithm Guard** before it is applied;
  rejected corrections fall back to the current safe algorithm.
- **No future CPU-burst values** may be fed to the LLM (burst-prediction rule).
- xv6 remains the execution authority; the simulator is the dev/fallback backend.
- This loop is independent of the **FAIL-only feedback** loop (which edits
  `prompt_feedback_rules.md` after a run); runtime correction acts *during* a run.

## 3. Target end-to-end flow

```
trace_<algo>.jsonl + metrics.json
        │
        ▼
  event_detector.py            ── runtime_events.json   (EXISTS)
        │  (problem detected at tick T, severity >= threshold)
        ▼
  correction_proposer.py       ── correction.json       (TODO)
        │   - rule-based default proposal (deterministic)
        │   - optional LLM refinement (no future bursts in prompt)
        ▼
  algorithm_guard.py (correction mode)  ── guard_decision(corrected)  (EXTEND)
        │   - reuse range/compat validation; reject -> keep current algo
        ▼
  backend applies at next scheduling point  (TODO)
        │   - simulator: switch algo/params between scheduling points
        │   - xv6: via setscheduler / setpredictor / setpriority syscalls
        ▼
  [SCHED] ... event=CORRECTION_APPLIED ... new_params={...}  (TODO emit)
        │
        ▼
  metrics + dashboard_live (TraceStack shows the correction)   (RENDER EXISTS)
```

## 4. Proposed `correction.json` contract

```json
{
  "trigger": { "type": "starvation", "tick": 80, "pid": 4, "severity": "high" },
  "from_algorithm": "MLFQ",
  "to_algorithm": "MLFQ",
  "params": { "aging_threshold": 20, "boost_interval": 80 },
  "apply_from_tick": 81,
  "reason": "Aging too weak; lower aging_threshold to rescue starved P4.",
  "source": "rule",
  "guard_validated": false
}
```
- `to_algorithm` may equal `from_algorithm` (parameter-only correction) or switch.
- `apply_from_tick` is always the **next** scheduling point after detection.
- `source` ∈ `rule | llm`. Rule proposals must work with no API key.

The applied event mirrors the existing demo shape:

```json
{ "tick": 81, "algo": "MLFQ", "event": "CORRECTION_APPLIED", "pid": -1,
  "correction_type": "parameter_update", "new_params": { "aging_threshold": 20, "boost_interval": 80 } }
```

## 5. Component responsibilities

- **correction_proposer.py** (new): `runtime_events.json` (+ `guard_decision.json`,
  `workload_summary.json`) → `correction.json`. Always produce a deterministic
  rule-based proposal per `type` (e.g. starvation → lower `aging_threshold` /
  shorten `boost_interval`; high_response_time → prefer RR/MLFQ shorter quantum;
  low_throughput → fewer preemptions). LLM refinement is optional and additive.
- **algorithm_guard.py** (extend): a correction-validation entry point that runs the
  existing algorithm/param-range checks on `correction.json` and sets
  `guard_validated` / falls back on reject. No new thresholds.
- **backend apply**:
  - *simulator*: between scheduling points, read the corrected algo/params and
    continue — deterministic and fully testable without xv6.
  - *xv6*: the orchestrator cannot change a running kernel today (no mid-run
    control channel). Options (future): a small control file/syscall the running
    `schedtest` polls at scheduling points, or re-issue `setscheduler` /
    `setpredictor` from a coordinating user process. Out of scope for the first slice.
- **tracer**: emit `CORRECTION_APPLIED` at `apply_from_tick` with `new_params`.

## 6. Recommended first slice (one safe PR)

Implement the loop **simulator-only and rule-based** (no LLM, no xv6):

1. `correction_proposer.py` with deterministic rules → `correction.json`.
2. Guard correction-validation in `algorithm_guard.py`.
3. `scheduler_simulator.py`: when a `runtime_events.json` problem exists, switch to
   the guard-validated corrected params at the next scheduling point and emit a
   `CORRECTION_APPLIED` trace event.
4. Orchestrator: wire detect → propose → guard → simulator apply for `--backend
   simulator`; write `correction.json` into live-data.

This proves the loop end-to-end deterministically and keeps the honest status:
LLM-assisted correction and xv6 mid-run application remain **Future Work**.

## 7. Safety checklist

- Guard re-validates every correction; reject → keep current algorithm.
- LLM prompt (if used) must exclude actual future bursts.
- Bound correction frequency (e.g. at most one correction per N ticks) to avoid
  thrashing; the LLM is invoked only on a detected event, never per tick.
- Correction applies only from `apply_from_tick` (next scheduling point).

## 8. Remaining work / risks

- xv6 mid-run application needs a control channel that does not exist yet — the
  largest open risk; first slice is simulator-only on purpose.
- Avoid correction thrashing (oscillating params).
- Keep `correction.json` aligned with `docs/dashboard_data_contract.md`.
- Until the full path (detect → propose → guard → apply → trace → dashboard) runs,
  this feature stays marked **Partial** in `docs/implementation_status.md`.
