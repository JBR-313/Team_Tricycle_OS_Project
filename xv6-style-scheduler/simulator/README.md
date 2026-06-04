# Scheduler Simulator (v1)

Host-side **fallback / dev** scheduling simulator for the **Team Tricycle OS**
project. It provides a scheduling execution and trace-generation layer for
local development.

This is **not** real xv6 execution. xv6 is the execution authority for the
project; this simulator exists so the rest of the pipeline (metrics, event
detector, dashboard) can be developed and tested without running QEMU.

## Purpose

Read a workload JSON, pick **one** scheduling algorithm (from a CLI flag or a
guard decision), simulate it tick-by-tick, and emit a **JSONL trace** that
follows the project-wide schema (`tick` / `algo` / `event` / `pid` / `state`).
The trace is the canonical artifact other roles consume (metrics, dashboard,
etc.).

This tool is intentionally narrow and host-side only:

- It does **not** modify xv6 source.
- It does **not** call any LLM API.
- It does **not** compute metrics or render a dashboard.
- It does **not** implement MLFQ or SRTF (see *Algorithm fallback* below).
- It does **not** simulate I/O sleep/wakeup (see *Workload schema* below).

The simulator is **deterministic**: the same workload + arguments always
produce a byte-identical trace. Every tie-break is fully specified.

## Location

```
Team_Tricycle_OS_Project/
├── workloads/                         # shared, repo-level workloads (inputs)
├── outputs/                           # guard_decision.json + generated traces
├── traces/                            # default place generated traces land
└── xv6-style-scheduler/
    └── simulator/
        ├── simulator.py
        └── README.md
```

Workloads are **not** duplicated under `simulator/`; the simulator
reads the repo-level `workloads/` directory.

## Supported algorithms

| Algorithm  | Preemptive? | Selection rule                                   | Tie-break                       |
|------------|-------------|--------------------------------------------------|---------------------------------|
| `RR`       | yes         | FIFO ready queue, sliced by time quantum         | preempted job goes to the back  |
| `FCFS`     | no          | smallest `arrival_time`                          | `pid`                           |
| `SJF`      | no          | smallest total CPU burst / remaining time        | `arrival_time`, then `pid`      |
| `PRIORITY` | no          | smallest priority number = highest priority      | `arrival_time`, then `pid`      |

- Algorithm names are **case-insensitive** (`rr`, `RR`, `Rr` all work).
- `SJF` support is included as a foundation for future burst-prediction experiments.
- `MLFQ`, `SRTF`, I/O sleep/wakeup, and xv6 hook changes are **future work**
  for this simulator path.

### Algorithm selection precedence

1. explicit `--algorithm`
2. `guard.algorithm`
3. `guard.scheduling_algorithm`
4. `guard.recommended_scheduling_algorithm`
5. `guard.selected_algorithm`
6. `guard.fallback_algorithm`
7. `guard.fallback_scheduling_algorithm`
8. `RR` (default)

### Algorithm fallback

If the resolved algorithm is unsupported (e.g. `MLFQ`):

1. use `guard.fallback_algorithm` / `guard.fallback_scheduling_algorithm`
   if it is supported, otherwise
2. fall back to `RR`.

Every substitution is reported on **stderr**. Example:

```
[simulator] WARNING: algorithm 'MLFQ' is not implemented in v1.
[simulator] WARNING: using guard fallback 'RR'.
```

### RR quantum precedence

1. `--quantum`
2. `guard.params.quantum`
3. `guard.parameters.time_quantum`
4. `10` (default, per `tools/README.md`)

## Workload schema (input)

A workload file is a **JSON array** of process objects. The simulator accepts
**both** the v1.5 single-burst format and the project-wide multi-burst format.

**Single-burst** (compact, v1.5-compatible):

```json
[
  { "pid": 1, "arrival_time": 0, "cpu_burst": 5,  "priority": 2, "type": "interactive" },
  { "pid": 2, "arrival_time": 1, "cpu_burst": 25, "priority": 3, "type": "cpu_bound" }
]
```

**Multi-burst** (`workloads/*.json`, the project-wide schema):

```json
[
  {
    "pid": 1,
    "arrival_time": 0,
    "cpu_bursts": [6, 4, 2],
    "io_bursts":  [3, 2],
    "priority": 5,
    "label": "cpu_bound"
  }
]
```

| Field          | Required | Rules                                                                                |
|----------------|----------|--------------------------------------------------------------------------------------|
| `pid`          | yes      | int or string; preserved verbatim in the trace                                       |
| `arrival_time` | yes      | integer, `>= 0`                                                                      |
| `cpu_burst`    | one of   | integer, `> 0`; used directly if present                                             |
| `cpu_bursts`   | one of   | non-empty list of positive integers; **flattened to `sum(cpu_bursts)` in v1**        |
| `io_bursts`    | no       | accepted for compatibility, **not simulated in v1** (no SLEEP/WAKEUP events emitted) |
| `priority`     | no       | integer; **defaults to 10**                                                          |
| `type`         | no       | free-form string; preserved for future trace extensions                              |
| `label`        | no       | alias for `type` (project-wide schema name); preserved similarly                     |

Rules:

- Exactly one of `cpu_burst` / `cpu_bursts` must be present. If `cpu_burst`
  is present it is used directly; otherwise the simulator uses
  `sum(cpu_bursts)` as the total CPU burst for v1.
- v1 does **not** model per-burst I/O. `io_bursts` is read for schema parity
  but does not generate any scheduler event.

Validation runs **before** any output is written, so an invalid workload never
produces a partial trace. Errors are printed to stderr and the process exits
with status `1`.

## Guard schema compatibility (input)

The simulator accepts a wide range of guard schemas. Pass one with `--guard`.

**Current repo schema** (`outputs/guard_decision.json`):

```json
{
  "guard_result": "accepted",
  "scheduling_algorithm": "RR",
  "params": { "quantum": 10 },
  "fallback_scheduling_algorithm": "RR"
}
```

**Older / simple schema:**

```json
{
  "selected_algorithm": "SJF",
  "fallback_algorithm": "RR",
  "parameters": { "time_quantum": 2 }
}
```

Only algorithm- and quantum-related keys are consumed; everything else is
ignored.

## Trace schema (output)

The trace is **JSONL**: one JSON object per line. Default location is
`traces/<workload>_<algorithm>.jsonl` (override with `--output`). The output
directory is created if it does not exist.

Every line carries these **primary** required fields:

| Field   | Meaning                                                      |
|---------|-------------------------------------------------------------|
| `tick`  | simulation tick                                             |
| `algo`  | the algorithm actually run (after any fallback)             |
| `event` | one of the events below                                     |
| `pid`   | process id (`null` for `IDLE`)                              |
| `state` | process/CPU state after the event                           |

For backward compatibility with v1.5 consumers, every line **also** carries
`time` (= `tick`) and `algorithm` (= `algo`) aliases.

**Core events:** `ARRIVE`, `DISPATCH`, `PREEMPT`, `EXIT`, `IDLE`,
`STARVATION_WARNING`
**Feedback evidence events** (trace-only, consumed later by the LLM feedback
loop; emitted with `pid: null` or the affected pid, and `state: "CONTROL"`):
`POLICY_FEEDBACK_SIGNAL`, `METRIC_SNAPSHOT`, `RUN_SUMMARY`
**States:** `RUNNABLE`, `RUNNING`, `ZOMBIE`, `IDLE`, `CONTROL`

### Event-specific fields

| Event                | Extra fields                                                                                                         |
|----------------------|----------------------------------------------------------------------------------------------------------------------|
| `ARRIVE`             | `queue: 0`, `priority`, `burst_hint: null`                                                                            |
| `DISPATCH`           | `queue: 0`                                                                                                            |
| `PREEMPT`            | `queue: 0`, `reason: "quantum_expired"` (RR)                                                                          |
| `EXIT`               | `queue: 0`, `state: "ZOMBIE"`, `turnaround`, `waiting`, `response`                                                    |
| `IDLE`               | `pid: null`, `state: "IDLE"`                                                                                          |
| `STARVATION_WARNING` | `waiting_since_tick`, `current_waiting_time`, `wait_time` (alias), `threshold`, `severity` (`"high"` / `"medium"`)    |

`burst_hint` is always `null`. Future CPU bursts are not exposed in the trace
(project-wide rule: predictors must not be fed actual future bursts).

Metric formulas used at `EXIT`:

```
response   = first_run_time - arrival_time
turnaround = finish_time    - arrival_time
waiting    = turnaround     - total_cpu_burst
```

Example (RR):

```json
{"tick": 0, "algo": "RR", "event": "ARRIVE",   "pid": 1, "state": "RUNNABLE", "time": 0, "algorithm": "RR", "queue": 0, "priority": 2, "burst_hint": null}
{"tick": 0, "algo": "RR", "event": "DISPATCH", "pid": 1, "state": "RUNNING",  "time": 0, "algorithm": "RR", "queue": 0}
{"tick": 5, "algo": "RR", "event": "EXIT",     "pid": 1, "state": "ZOMBIE",   "time": 5, "algorithm": "RR", "queue": 0, "turnaround": 5, "waiting": 0, "response": 0}
```

### STARVATION_WARNING event

```json
{
  "tick": 10,
  "algo": "SJF",
  "event": "STARVATION_WARNING",
  "pid": 2,
  "state": "RUNNABLE",
  "time": 10,
  "algorithm": "SJF",
  "waiting_since_tick": 0,
  "current_waiting_time": 10,
  "wait_time": 10,
  "threshold": 10,
  "severity": "medium"
}
```

`severity` is `"high"` when `current_waiting_time >= threshold * 2`,
`"medium"` otherwise.

### Feedback evidence events

These events are produced for the downstream LLM feedback loop. They carry
`state: "CONTROL"` and either `pid: null` or the pid the signal concerns.
They are silently ignored by `tools/metrics.py` (no impact on per-process
accounting, regret, or judgment).

#### `POLICY_FEEDBACK_SIGNAL`

Emitted when the current execution shows a feedback-worthy issue. Deterministic
conservative thresholds:

| `signal_type`         | When emitted                                                                                                |
|-----------------------|-------------------------------------------------------------------------------------------------------------|
| `starvation_risk`     | at the same tick as a `STARVATION_WARNING` (once per waiting period per pid)                                |
| `high_waiting_time`   | when a runnable process's `current_waiting_time >= starvation_threshold` (paired with `starvation_risk`)    |
| `preemption_overhead` | under RR, the first tick that `preemption_count_so_far >= max(4, total_process_count * 2)` (latched, once)  |

Fields:

```json
{
  "tick": 100, "algo": "SJF", "event": "POLICY_FEEDBACK_SIGNAL",
  "pid": 2, "state": "CONTROL",
  "signal_type": "starvation_risk",
  "target_metric": "max_waiting_time",
  "current_value": 99, "threshold": 10, "deviation_ratio": 9.9,
  "affected_pids": [2],
  "severity": "high",
  "feedback_hint": "SJF may reduce average waiting time but can starve long jobs on this workload."
}
```

`severity` is `"high"` when `deviation_ratio >= 2.0`, otherwise `"medium"`.
`feedback_hint` is a short algorithm-specific note the LLM can quote.

#### `METRIC_SNAPSHOT`

Opt-in via `--feedback-snapshot-interval N` (default `0`, disabled). When
`N > 0`, emitted at dispatch boundaries whenever
`tick - last_snapshot_tick >= N`.

Fields: `completed_count`, `total_process_count`, `ready_queue_len`,
`runnable_count`, `preemption_count_so_far`, `starvation_warning_count_so_far`,
`idle_ticks_so_far`, `cpu_busy_ticks_so_far`, `cpu_utilization_so_far`,
`max_ready_queue_len`, `max_waiting_observed`.

#### `RUN_SUMMARY`

Always emitted once, on the final tick of the trace.

Fields: `completed_count`, `total_process_count`, `total_ticks`,
`preemption_count`, `starvation_warning_count`, `idle_ticks`, `cpu_busy_ticks`,
`cpu_utilization`, `max_ready_queue_len`, `max_waiting_observed`,
`feedback_signal_count`, `high_severity_signal_count`.

## Starvation warning rule

Configured with `--starvation-threshold N` (default `20`; `0` or negative
disables it).

- Each process tracks `ready_since`.
- `ready_since` is set to the current tick when the process **ARRIVE**s and
  is reset when it is **PREEMPT**ed (a new waiting period begins).
- At every dispatch decision, before choosing the next process, each **other**
  runnable process (i.e. the ones being passed over) is checked:
  if `current_tick - ready_since >= threshold` and it has **not** already
  warned in the current waiting period, a `STARVATION_WARNING` is emitted and
  the process is marked as warned.
- A single waiting period emits **at most one** warning (no spam).
- Once a process is dispatched and later becomes runnable again (e.g. RR
  preemption), its warning status resets and it may warn again.

The process actually being dispatched never warns — it is not starving, it is
about to run.

## CLI

```
python3 simulator.py --workload <path> [options]

  --workload PATH              (required) workload JSON array
  --algorithm NAME             RR | FCFS | SJF | PRIORITY (case-insensitive)
  --guard PATH                 guard_decision.json (any supported schema)
  --output PATH                trace path; default traces/<workload>_<algo>.jsonl
  --quantum N                  RR time quantum (default 10)
  --starvation-threshold N     warn after N waiting ticks (default 20; 0 disables)
  --feedback-snapshot-interval N
                               emit a METRIC_SNAPSHOT at dispatch boundaries
                               every >= N ticks (default 0; disabled)
```

Paths in the examples below are relative to the **repo root**
(`Team_Tricycle_OS_Project/`).

## Example commands

```bash
# Round Robin, explicit quantum, starvation threshold 20
python3 xv6-style-scheduler/simulator/simulator.py \
  --workload workloads/mixed_workload.json \
  --algorithm RR \
  --output outputs/trace_mixed_rr.jsonl \
  --quantum 10 \
  --starvation-threshold 20

# Priority (non-preemptive); pid 4 has no priority -> defaults to 10
python3 xv6-style-scheduler/simulator/simulator.py \
  --workload workloads/priority_sensitive.json \
  --algorithm PRIORITY \
  --output outputs/trace_priority.jsonl \
  --starvation-threshold 10

# SJF with a long job that gets starved -> STARVATION_WARNING events
python3 xv6-style-scheduler/simulator/simulator.py \
  --workload workloads/starvation_risk.json \
  --algorithm SJF \
  --output outputs/trace_starvation_sjf.jsonl \
  --starvation-threshold 10

# Let the guard decide the algorithm (and quantum)
python3 xv6-style-scheduler/simulator/simulator.py \
  --workload workloads/mixed_workload.json \
  --guard outputs/guard_decision.json \
  --output outputs/trace_mixed_guard_selected.jsonl

# Feedback evidence: paired POLICY_FEEDBACK_SIGNAL + METRIC_SNAPSHOT
# (RUN_SUMMARY is always emitted at end of trace)
python3 xv6-style-scheduler/simulator/simulator.py \
  --workload workloads/starvation_risk.json \
  --algorithm SJF \
  --output outputs/trace_feedback_sjf.jsonl \
  --starvation-threshold 10 \
  --feedback-snapshot-interval 10
```

## Limitations (v1)

- Multi-burst workloads are flattened to a single total via `sum(cpu_bursts)`;
  no per-burst granularity.
- `io_bursts` is read but not simulated; no `SLEEP` / `WAKEUP` events.
- No MLFQ (and therefore no `QUEUE_CHANGE` events with `from_queue` /
  `to_queue`).
- No SRTF (preemptive shortest remaining).
- No xv6 hook changes — the simulator is host-side only.
- No runtime correction event (`CORRECTION_APPLIED`).
