# MLFQ Queue Visualization Review

> **Scope:** Whether `dashboard_live` makes MLFQ's three-queue structure
> (Q0/Q1/Q2) and `QUEUE_CHANGE` events visible to the demo audience.
> Status: 2026-05-28, branch `feat/upstage-runtime-strict`.

---

## 1. What the data already contains

The xv6 kernel and the simulator both emit MLFQ queue information:

| Source | Event line / record |
|---|---|
| xv6 kernel (`xv6-riscv/kernel/proc.c:613-620` `sched_trace_queue`) | `[SCHED] tick=N algo=MLFQ event=QUEUE_CHANGE pid=N from_queue=X to_queue=Y reason=…` |
| xv6 kernel (`proc.c:592-611` `sched_trace`) | every `DISPATCH` / `PREEMPT` line includes `queue=Q` |
| simulator (`tools/scheduler_simulator.py:147-155, 197-204`) | `QUEUE_CHANGE` with `from_queue`/`to_queue`/`reason` (`aging_promotion`, `demotion`) |
| trace_parser (`tools/trace_parser.py`) | passes through as `{tick, algo, event:"QUEUE_CHANGE", pid, from_queue, to_queue, reason}` |

So **the data is there**. The question is what the dashboard does with it.

## 2. What the dashboard shows today

### 2.1 Header / per-algo (`Header.jsx`)
Shows the active algorithm name. No queue-aware UI.

### 2.2 `MainGantt.jsx`
Single horizontal bar per CPU (one CPU under `CPUS=1`). No queue lane —
each DISPATCH block is colored by PID, not by `queue`.

### 2.3 `ProcessLanes.jsx`
One row per PID. The lane segments come from `DISPATCH → PREEMPT/SLEEP/EXIT`
windows. The `queue` field is read into `buildSegments` only as
documentation; it does **not** drive any visual property. Verified:
`grep -n "queue\|MLFQ\|level" dashboard_live/src/components/ProcessLanes.jsx`
returns no matches.

### 2.4 `TraceStack.jsx`
Lists every event with an icon. `QUEUE_CHANGE` has dedicated entries:

```js
// dashboard_live/src/components/TraceStack.jsx:6, 18
ARRIVE: '→', WAKEUP: '↑', QUEUE_CHANGE: '⇄', CORRECTION_APPLIED: '⚡',
QUEUE_CHANGE: { text: 'QUEUE', color: '#b45309', bg: 'rgba(254,243,199,0.85)' },
```

So a `QUEUE_CHANGE` shows up in the trace list with a `⇄` icon and amber
background. **It is the only place in the dashboard where the queue
transition is visible.**

### 2.5 `ProcessState.jsx`
RUNNING/RUNNABLE/SLEEPING/ZOMBIE table. No queue column.

### 2.6 Other cards
`LLMRecommendation` shows MLFQ params (`quantum:[2,4,8]`, etc.) when the LLM
chose MLFQ, but does not surface live queue state.

## 3. The gap

For an MLFQ demo, the audience should be able to answer two questions at a
glance:

1. **“What is currently in Q0 vs Q1 vs Q2?”** — today: not visible.
2. **“When did a process get demoted / promoted, and why?”** — today: only
   as one row in the long `TraceStack` list.

This matters because MLFQ is the algorithm the LLM picks most often (see
`workload_coverage_matrix.md`). If the audience cannot see *why* MLFQ won,
the win looks unmotivated.

## 4. Proposal: MLFQ Queue Panel (small, focused)

A single new card, `MLFQQueuePanel.jsx`, rendered **only when**
`algo === 'MLFQ'`. Three sub-views inside one card so it does not increase
card count noticeably.

### 4.1 Sub-view A — current queue snapshot

Three lanes labelled `Q0 (quantum=2)`, `Q1 (quantum=4)`, `Q2 (quantum=8)`.
For each PID with at least one event up to `currentTick`, place its chip in
the lane that matches its most-recent `queue` field
(`DISPATCH`/`PREEMPT`/`QUEUE_CHANGE.to_queue`/`ARRIVE.queue` whichever was
latest).

Example layout (ASCII):

```
┌─ Q0  quantum=2 ──────────────────────────┐
│  ● P3 (RUNNING)   ● P5                   │
├─ Q1  quantum=4 ──────────────────────────┤
│  ● P1                                    │
├─ Q2  quantum=8 ──────────────────────────┤
│  ● P2   ● P4                             │
└──────────────────────────────────────────┘
```

State is computed by folding events up to `currentTick` — pure derived
state, no new fetcher.

### 4.2 Sub-view B — Recent Queue Changes (last 5)

A small chronological list under the queue snapshot:

```
tick 14 · P2  Q0 → Q1 · demotion (quantum_expired)
tick 23 · P4  Q1 → Q0 · aging_promotion
tick 41 · P2  Q1 → Q2 · demotion
…
```

Source: `events.filter(e => e.event === 'QUEUE_CHANGE').slice(-5)`.

### 4.3 Sub-view C — Per-queue dispatch share

Three thin horizontal bars showing what fraction of total dispatches went
to each queue level. Built from
`events.filter(e => e.event === 'DISPATCH').groupBy(e => e.queue)`.

This is the single number that answers “did MLFQ actually behave like an
MLFQ?” in two seconds.

### 4.4 Visibility rule

```jsx
{algo === 'MLFQ' && <MLFQQueuePanel events={events} currentTick={tick} />}
```

The panel is **invisible** for the other five algorithms so it does not add
visual noise.

## 5. Effort & risk

| Item | Estimate |
|---|---|
| New component `MLFQQueuePanel.jsx` | ~120 lines, no new dependencies |
| App wire-up in `dashboard_live/src/App.jsx` (one conditional render) | ~3 lines |
| CSS for queue lanes / chips (`App.css`) | ~40 lines |
| Tests / snapshots | none today (no test infra) |
| Risk to other cards | none — pure derived state, no new data fetches |

Total: ~half a day, single PR.

## 6. Smaller alternative (if even that is too much)

If the queue-panel PR cannot land before the demo, the minimum-viable
patch is:

1. Add a `queue=Q` chip to each row in `ProcessState.jsx` (one new column).
2. Filter `TraceStack.jsx` with a “MLFQ queue events only” toggle when
   `algo === 'MLFQ'` so the audience can scroll through queue history
   without unrelated events.

Both are < 20 lines each.

## 7. Recommendation

| Priority | Action | Rationale |
|---|---|---|
| **P1** | Build `MLFQQueuePanel.jsx` per §4. | Makes the LLM's most-chosen algorithm visibly *justified*. |
| P0 fallback | Add the small `ProcessState.jsx` queue column + `TraceStack.jsx` filter from §6. | If the panel slips, the queue is still readable. |
| P2 | Show predictor `predicted_burst` next to SJF/SRTF chips in a future “Predictor Panel” (mirrors this design). | Out of scope for this review; logged for completeness. |

For the final demo: **ship at least §6 (P0 fallback). Aim for §4 if a
half-day slot is available.**

## 8. Acceptance test

After the change, an audience member must be able to, in ≤ 5 seconds:

1. Identify which PIDs are currently in Q0.
2. Tell whether the latest `QUEUE_CHANGE` was a promotion or a demotion.
3. See that MLFQ actually used Q1 and Q2 (i.e. queue dispatch share is not
   100% Q0).
