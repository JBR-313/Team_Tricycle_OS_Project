# LLM Sched Copilot — Scheduling Trace Log Format

## Overview

The Scheduling Trace Log is the primary data interface between the xv6 kernel (or Scheduler Simulator) and all downstream modules.

Format: **JSON Lines (JSONL)** — one JSON object per line, newline-delimited.  
File: `outputs/trace.jsonl`

Each line represents one scheduling event.

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

### CORRECTION_APPLIED

A runtime correction proposed by the LLM and validated by Algorithm Guard has been applied.

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
