# LLM Sched Copilot — Scheduling Trace Log Format

## Overview

The Scheduling Trace Log is the primary data interface between the xv6 kernel (or Scheduler Simulator) and all downstream modules.

Format: **JSON Lines (JSONL)** — one JSON object per line, newline-delimited.  
File: `outputs/trace.jsonl`

Each line represents one scheduling event.

The normalized JSONL described below is produced by `tools/trace_parser.py` from
the **raw console log lines** that xv6 prints. Two raw line shapes exist: kernel
`[SCHED]` lines and user-program `[SCHEDTEST]` metadata lines. Both are
documented in "Raw xv6 Console Log Format" before the normalized fields.

---

## Raw xv6 Console Log Format

xv6 cannot write JSON files from inside the guest. Instead it prints plain text
lines to the QEMU console, and `tools/trace_parser.py` converts them into the
normalized JSONL described in the rest of this document. Only lines containing
`[SCHED]` or `[SCHEDTEST]` are processed; boot spam and shell prompts are
ignored.

### Kernel scheduling lines — `[SCHED]`

Emitted by the xv6 kernel scheduler.

```text
[SCHED] tick=<int> algo=<ALGO> event=<EVENT> pid=<int> state=<STATE> queue=<int> priority=<int> reason=<text>
```

Events emitted today: `DISPATCH`, `PREEMPT`, `EXIT`, `QUEUE_CHANGE`,
`ARRIVE`, `SLEEP`, `WAKEUP`. The simulator additionally emits `PRED_UPDATE`
(SJF/SRTF EMA refresh). Tokens are generic `key=value` pairs; not every
token is present on every line.

**Per-event optional fields (loaders MUST tolerate missing keys):**

| Event | Required | Optional |
|---|---|---|
| `ARRIVE` | `tick`, `pid` | `state`, `queue`, `priority` |
| `DISPATCH` | `tick`, `pid` | `state`, `queue`, `priority` |
| `PREEMPT` | `tick`, `pid` | `state`, `queue`, `priority`, `reason` |
| `EXIT` | `tick`, `pid` | `state`, `queue`, `turnaround`, `waiting`, `response` |
| `QUEUE_CHANGE` | `tick`, `pid`, `from_queue`, `to_queue` | `reason` (`demotion` / `aging_promotion` / `promotion`) |
| `SLEEP` / `WAKEUP` | `tick`, `pid` | `state` |
| `PRED_UPDATE` (simulator) | `tick`, `pid`, `observed`, `predicted_prev`, `predicted_next` | `source` (`ema` or `llm`) |

> The spec-suggested discrete events `QUEUE_ENTER` / `QUEUE_LEAVE` /
> `DEMOTE` / `PROMOTE` are **expressed** in this project as
> `QUEUE_CHANGE` with `reason=demotion|aging_promotion|promotion` and the
> `from_queue` / `to_queue` pair. Consumers that want the discrete view
> should derive it from `QUEUE_CHANGE`. The parser preserves any unknown
> tokens via its "carry every remaining token through" rule
> (`tools/trace_parser.py:137-141`), so a future kernel patch can switch to
> discrete events without breaking the parser.

```text
[SCHED] tick=12 algo=MLFQ event=DISPATCH pid=3 state=RUNNING queue=0 priority=2
[SCHED] tick=2 algo=MLFQ event=PREEMPT pid=1 state=RUNNABLE queue=1 priority=1 reason=quantum_expired
[SCHED] tick=30 algo=MLFQ event=QUEUE_CHANGE pid=1 state=RUNNABLE from_queue=0 to_queue=1 reason=demotion
[SCHED] tick=60 algo=MLFQ event=EXIT pid=2 state=ZOMBIE queue=1 turnaround=58 waiting=50 response=2
```

> Status note: the full set of rich `[SCHED]` events is part of the in-progress
> xv6 backend. Not all events are emitted by the kernel yet.

### User-program metadata lines — `[SCHEDTEST]`

Emitted by the `schedtest.c` user program to describe the run and the processes
it defines. These lines provide run context (seed, profile, process definitions)
that the kernel scheduler does not know.

```text
[SCHEDTEST] event=RUN_BEGIN|PROC_DEF|CHILD_START|CHILD_EXIT|RUN_END key=value ...
```

```text
[SCHEDTEST] event=RUN_BEGIN algo=MLFQ seed=42 profile=interactive
[SCHEDTEST] event=PROC_DEF pid=3 arrival=0 cpu_burst=5 priority=2 label=interactive
[SCHEDTEST] event=CHILD_START pid=3 priority=2
[SCHEDTEST] event=CHILD_EXIT pid=3
[SCHEDTEST] event=RUN_END algo=MLFQ seed=42 profile=interactive
```

> Status note: `schedtest.c` currently takes only `schedtest <algo>`. The
> planned `schedtest <algorithm> <seed> <profile>` form, and the `[SCHEDTEST]`
> metadata emission, are PLANNED / in-progress, not done.

### Parser CLI

```bash
python3 tools/trace_parser.py --input <log> --algo <ALGO> \
    [--out <file> | --out-dir <dir>] [--seed N] [--profile P]
```

- `--input` — raw xv6 console log file.
- `--algo` — algorithm name (`RR`, `FCFS`, `PRIORITY`, `MLFQ`, `SJF`, `SRTF`);
  used when a line omits its own `algo` token.
- `--out` — output JSONL path (default `outputs/trace.jsonl`).
- `--out-dir` — alternative to `--out`; writes `trace_<algo>.jsonl` into the dir.
- `--seed` / `--profile` — optional; stamped onto every emitted event.

### Normalized JSONL fields (parser output)

`tools/trace_parser.py` emits one normalized JSON object per recognized line:

| Field | Source |
|-------|--------|
| `tick` | `tick` token (integer, or `null` for `[SCHEDTEST]` metadata) |
| `algo` | `algo` token, canonicalized to UPPERCASE, falling back to `--algo` |
| `event` | `event` token |
| `pid` | `pid` token |
| `state` | `state` token |
| `queue` / `priority` / `reason` | carried through when present |
| `from_queue` / `to_queue` | carried through (QUEUE_CHANGE) |
| `turnaround` / `waiting` / `response` | carried through (EXIT) |
| `source` | always `"xv6"` |
| `kind` | `"sched"` for `[SCHED]` lines, `"schedtest"` for `[SCHEDTEST]` lines |
| `seed` / `profile` | added when `--seed` / `--profile` are supplied |

Integer-looking tokens (`tick`, `pid`, `queue`, `priority`, `from_queue`,
`to_queue`, `turnaround`, `waiting`, `response`, `arrival`, `cpu_burst`, `seed`)
are coerced to integers; all other values stay as strings. Events are stably
sorted by `tick`, with null-tick metadata lines treated as `-1` so `RUN_BEGIN`
and related lines stay at the front.

---

## Common Fields

Every event line must include the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `tick` | integer | xv6 tick count when the event occurred |
| `algo` | string | Scheduling Algorithm active at the time of the event |
| `event` | string | Event type (see below) |
| `pid` | integer | Process ID involved in the event |
| `state` | string | Process state after the event |

Optional fields may appear depending on the event type.

---

## Event Types

### ARRIVE

A new process has arrived (been created or entered the ready queue for the first time).

```json
{"tick": 0,  "algo": "RR",    "event": "ARRIVE",   "pid": 1, "state": "RUNNABLE", "queue": 0, "priority": 5, "burst_hint": null}
{"tick": 3,  "algo": "MLFQ",  "event": "ARRIVE",   "pid": 2, "state": "RUNNABLE", "queue": 0, "priority": 3, "burst_hint": null}
```

| Field | Notes |
|-------|-------|
| `queue` | Queue level (0 = highest priority queue). 0 for non-MLFQ algorithms. |
| `priority` | Initial process priority. |
| `burst_hint` | Always `null`. Future CPU bursts must not be given to the LLM or recorded here. |

---

### DISPATCH

The scheduler has selected this process and it has started running on CPU.

```json
{"tick": 1,  "algo": "RR",    "event": "DISPATCH", "pid": 1, "state": "RUNNING",  "queue": 0}
{"tick": 5,  "algo": "MLFQ",  "event": "DISPATCH", "pid": 2, "state": "RUNNING",  "queue": 0}
```

| Field | Notes |
|-------|-------|
| `queue` | Queue level from which the process was dispatched. |

---

### PREEMPT

The running process has been preempted (time quantum expired or higher-priority process arrived).

```json
{"tick": 5,  "algo": "RR",    "event": "PREEMPT",  "pid": 1, "state": "RUNNABLE", "queue": 0, "reason": "quantum_expired"}
{"tick": 12, "algo": "MLFQ",  "event": "PREEMPT",  "pid": 2, "state": "RUNNABLE", "queue": 1, "reason": "quantum_expired"}
```

| Field | Notes |
|-------|-------|
| `reason` | `"quantum_expired"` or `"higher_priority_arrived"` |

---

### SLEEP

The process has voluntarily yielded the CPU and is waiting for an I/O event or sleep call.

```json
{"tick": 8,  "algo": "RR",    "event": "SLEEP",    "pid": 3, "state": "SLEEPING", "queue": 0}
```

---

### WAKEUP

The process has been woken up from sleep and re-entered the ready queue.

```json
{"tick": 15, "algo": "RR",    "event": "WAKEUP",   "pid": 3, "state": "RUNNABLE", "queue": 0}
```

---

### EXIT

The process has finished execution and exited.

```json
{"tick": 22, "algo": "RR",    "event": "EXIT",     "pid": 1, "state": "ZOMBIE",   "queue": 0, "turnaround": 22, "waiting": 14, "response": 1}
```

| Field | Notes |
|-------|-------|
| `turnaround` | `finish_time - arrival_time` |
| `waiting` | `turnaround_time - total_cpu_burst_time` |
| `response` | `first_run_time - arrival_time` |

---

### QUEUE_CHANGE

A process has moved from one MLFQ queue to another (demotion or aging promotion).

```json
{"tick": 30, "algo": "MLFQ",  "event": "QUEUE_CHANGE", "pid": 4, "state": "RUNNABLE", "from_queue": 0, "to_queue": 1, "reason": "demotion"}
{"tick": 80, "algo": "MLFQ",  "event": "QUEUE_CHANGE", "pid": 5, "state": "RUNNABLE", "from_queue": 2, "to_queue": 0, "reason": "aging"}
```

| Field | Notes |
|-------|-------|
| `from_queue` | Previous queue level. |
| `to_queue` | New queue level. |
| `reason` | `"demotion"` (used full quantum) or `"aging"` (waited too long) or `"boost"` (periodic boost). |

---

### CORRECTION_APPLIED *(Future Work — not emitted today)*

> Reserved trace event for the closed-loop runtime-correction path.
> The current pipeline ships **preview-only** correction artifacts
> (`runtime_events.json`, `correction_proposal.json`,
> `correction_guard_decision.json`) and does **not** emit
> `CORRECTION_APPLIED`. The schema below is the design target.

When the closed loop is wired, a runtime correction proposed and
guard-validated would be applied at the next scheduling point.

```json
{"tick": 45, "algo": "MLFQ",  "event": "CORRECTION_APPLIED", "pid": -1, "state": null, "correction_type": "parameter_update", "new_params": {"aging_threshold": 20, "boost_interval": 80}}
{"tick": 60, "algo": "Priority", "event": "CORRECTION_APPLIED", "pid": -1, "state": null, "correction_type": "algorithm_change", "new_algo": "MLFQ"}
```

| Field | Notes |
|-------|-------|
| `pid` | `-1` — this event applies to the scheduler, not a specific process. |
| `state` | `null` |
| `correction_type` | `"parameter_update"`, `"algorithm_change"`, `"aging_threshold_adjustment"`, `"quantum_adjustment"` |
| `new_params` | Updated parameters (present for `parameter_update` corrections). |
| `new_algo` | New Scheduling Algorithm (present for `algorithm_change` corrections). |

---

## Full Example Trace

```jsonl
{"tick": 0,  "algo": "RR", "event": "ARRIVE",   "pid": 1, "state": "RUNNABLE", "queue": 0, "priority": 5, "burst_hint": null}
{"tick": 0,  "algo": "RR", "event": "DISPATCH",  "pid": 1, "state": "RUNNING",  "queue": 0}
{"tick": 3,  "algo": "RR", "event": "ARRIVE",    "pid": 2, "state": "RUNNABLE", "queue": 0, "priority": 3, "burst_hint": null}
{"tick": 4,  "algo": "RR", "event": "PREEMPT",   "pid": 1, "state": "RUNNABLE", "queue": 0, "reason": "quantum_expired"}
{"tick": 4,  "algo": "RR", "event": "DISPATCH",  "pid": 2, "state": "RUNNING",  "queue": 0}
{"tick": 8,  "algo": "RR", "event": "SLEEP",     "pid": 2, "state": "SLEEPING", "queue": 0}
{"tick": 8,  "algo": "RR", "event": "DISPATCH",  "pid": 1, "state": "RUNNING",  "queue": 0}
{"tick": 12, "algo": "RR", "event": "WAKEUP",    "pid": 2, "state": "RUNNABLE", "queue": 0}
{"tick": 16, "algo": "RR", "event": "PREEMPT",   "pid": 1, "state": "RUNNABLE", "queue": 0, "reason": "quantum_expired"}
{"tick": 16, "algo": "RR", "event": "DISPATCH",  "pid": 2, "state": "RUNNING",  "queue": 0}
{"tick": 20, "algo": "RR", "event": "EXIT",      "pid": 1, "state": "ZOMBIE",   "queue": 0, "turnaround": 20, "waiting": 8, "response": 0}
{"tick": 24, "algo": "RR", "event": "EXIT",      "pid": 2, "state": "ZOMBIE",   "queue": 0, "turnaround": 21, "waiting": 5, "response": 1}
```

---

## Rules

- `burst_hint` must always be `null`. Future CPU bursts must not be recorded.
- Every DISPATCH must be preceded by either an ARRIVE or a WAKEUP for the same `pid`.
- Every EXIT must terminate the process — no further events for that `pid` should appear.
- QUEUE_CHANGE is only valid when `algo` is `MLFQ` or `Priority` (for aging events).
- CORRECTION_APPLIED uses `pid: -1` and `state: null`.
- All times are in xv6 tick units.
