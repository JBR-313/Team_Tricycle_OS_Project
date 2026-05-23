# Scheduler Simulator (v1.5)

Host-side scheduling simulator for the **Team Tricycle OS** project.
It provides the scheduling execution and trace-generation layer for the system.

## Purpose

Read a workload JSON, pick **one** scheduling algorithm (from a CLI flag or a
guard decision), simulate it tick-by-tick, and emit a **JSONL trace** of every
scheduler event. The trace is the canonical artifact other roles consume
(metrics, dashboard, etc.).

This tool is intentionally narrow and host-side only:

- It does **not** modify xv6 source.
- It does **not** call any LLM API.
- It does **not** compute metrics or render a dashboard.
- It does **not** implement MLFQ or SRTF (see *Algorithm fallback* below).

The simulator is **deterministic**: the same workload + arguments always
produce a byte-identical trace. Every tie-break is fully specified.

## Location

```
Team_Tricycle_OS_Project/
├── workloads/                         # shared, repo-level workloads (inputs)
├── outputs/                           # guard_decision.json lives here
├── traces/                            # default place generated traces land
└── xv6-style-scheduler/
    └── scheduler_simulator/
        ├── simulator.py
        └── README.md
```

Workloads are **not** duplicated under `scheduler_simulator/`; the simulator
reads the repo-level `workloads/` directory.

## Supported algorithms

| Algorithm  | Preemptive? | Selection rule                                   | Tie-break                       |
|------------|-------------|--------------------------------------------------|---------------------------------|
| `RR`       | yes         | FIFO ready queue, sliced by time quantum         | preempted job goes to the back  |
| `FCFS`     | no          | smallest `arrival_time`                          | `pid`                           |
| `SJF`      | no          | smallest `cpu_burst` / `remaining_time`          | `arrival_time`, then `pid`      |
| `PRIORITY` | no          | smallest priority number = highest priority      | `arrival_time`, then `pid`      |

- Algorithm names are **case-insensitive** (`rr`, `RR`, `Rr` all work).
- `SJF` support is included as a foundation for future burst-prediction experiments.
- `MLFQ` and `SRTF` are **not implemented** in v1.5.

### Algorithm selection precedence

1. explicit `--algorithm`
2. `guard.algorithm` (current repo schema)
3. `guard.selected_algorithm` (legacy schema)
4. `guard.fallback_algorithm`
5. `RR` (default)

### Algorithm fallback

If the resolved algorithm is unsupported (e.g. `MLFQ`):

1. use `guard.fallback_algorithm` if it is supported, otherwise
2. fall back to `RR`.

Every substitution is reported on **stderr**. Example:

```
[simulator] WARNING: algorithm 'MLFQ' is not implemented in v1.5.
[simulator] WARNING: using guard fallback_algorithm 'RR'.
```

### RR quantum precedence

1. `--quantum`
2. `guard.params.quantum` (current repo schema)
3. `guard.parameters.time_quantum` (legacy schema)
4. `10` (default, per `tools/README.md`)

## Workload schema (input)

A workload file is a **JSON array** of process objects (note: an array, not an
object; the CPU field is `cpu_burst`, not `burst_time`):

```json
[
  { "pid": 1, "arrival_time": 0, "cpu_burst": 5,  "priority": 2, "type": "interactive" },
  { "pid": 2, "arrival_time": 1, "cpu_burst": 25, "priority": 3, "type": "cpu_bound" }
]
```

| Field          | Required | Rules                                                      |
|----------------|----------|-----------------------------------------------------------|
| `pid`          | yes      | int or string; preserved verbatim in the trace            |
| `arrival_time` | yes      | integer, `>= 0`                                            |
| `cpu_burst`    | yes      | integer, `> 0`                                             |
| `priority`     | no       | integer; **defaults to 10** (a safe neutral value)        |
| `type`         | no       | free-form string (e.g. `interactive`, `cpu_bound`); preserved for future trace extensions |

Validation runs **before** any output is written, so an invalid workload never
produces a partial trace. Errors are printed to stderr and the process exits
with status `1`.

## Guard schema compatibility (input)

The simulator accepts both guard schemas. Pass one with `--guard`.

**Current repo schema** (`outputs/guard_decision.json`):

```json
{
  "guard_result": "accepted",
  "algorithm": "RR",
  "params": { "quantum": 10 },
  "target_metric": "response_time",
  "compatibility_score": 0.95,
  "confidence_score": 0.85,
  "reason": "Accepted...",
  "fallback_algorithm": "RR",
  "warnings": []
}
```

**Legacy / simple schema:**

```json
{
  "selected_algorithm": "SJF",
  "fallback_algorithm": "RR",
  "parameters": { "time_quantum": 2 }
}
```

Only the algorithm/quantum-related keys are consumed; everything else is ignored.

## Trace schema (output)

The trace is **JSONL**: one JSON object per line. Default location is
`traces/<workload>_<algorithm>.jsonl` (override with `--output`). The output
directory is created if it does not exist.

Every line carries these required fields:

| Field       | Meaning                                                      |
|-------------|-------------------------------------------------------------|
| `time`      | simulation tick                                             |
| `event`     | one of the events below                                     |
| `pid`       | process id (`null` for `IDLE`)                              |
| `algorithm` | the algorithm actually run (after any fallback)             |
| `state`     | process/CPU state after the event                           |

**Core events:** `ARRIVE`, `DISPATCH`, `PREEMPT`, `EXIT`, `IDLE`
**States:** `RUNNABLE`, `RUNNING`, `TERMINATED`, `IDLE`

Example (RR):

```json
{"time": 0, "event": "ARRIVE",   "pid": 1, "algorithm": "RR", "state": "RUNNABLE"}
{"time": 0, "event": "DISPATCH", "pid": 1, "algorithm": "RR", "state": "RUNNING"}
{"time": 5, "event": "EXIT",     "pid": 1, "algorithm": "RR", "state": "TERMINATED"}
```

### STARVATION_WARNING event

Emitted with two extra fields:

```json
{
  "time": 10,
  "event": "STARVATION_WARNING",
  "pid": 2,
  "algorithm": "SJF",
  "state": "RUNNABLE",
  "wait_time": 10,
  "threshold": 10
}
```

## Starvation warning rule

Configured with `--starvation-threshold N` (default `20`; `0` or negative
disables it).

- Each process tracks `ready_since`.
- `ready_since` is set to the current time when the process **ARRIVE**s and is
  reset when it is **PREEMPT**ed (a new waiting period begins).
- At every dispatch decision, before choosing the next process, each **other**
  runnable process (i.e. the ones being passed over) is checked:
  if `current_time - ready_since >= threshold` and it has **not** already warned
  in the current waiting period, a `STARVATION_WARNING` is emitted and the
  process is marked as warned.
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
  --guard PATH                 guard_decision.json (either schema)
  --output PATH                trace path; default traces/<workload>_<algo>.jsonl
  --quantum N                  RR time quantum (default 10)
  --starvation-threshold N     warn after N waiting ticks (default 20; 0 disables)
```

Paths in the examples below are relative to the **repo root**
(`Team_Tricycle_OS_Project/`).

## Example commands

```bash
# Round Robin, explicit quantum, starvation threshold 20
python3 xv6-style-scheduler/scheduler_simulator/simulator.py \
  --workload workloads/mixed_workload.json \
  --algorithm RR \
  --output traces/mixed_rr.jsonl \
  --quantum 10 \
  --starvation-threshold 20

# Priority (non-preemptive); pid 4 has no priority -> defaults to 10
python3 xv6-style-scheduler/scheduler_simulator/simulator.py \
  --workload workloads/priority_sensitive.json \
  --algorithm PRIORITY \
  --output traces/priority_trace.jsonl \
  --starvation-threshold 10

# SJF with a long job that gets starved -> one STARVATION_WARNING at t=10
python3 xv6-style-scheduler/scheduler_simulator/simulator.py \
  --workload workloads/starvation_risk.json \
  --algorithm SJF \
  --output traces/starvation_sjf.jsonl \
  --starvation-threshold 10

# Let the guard decide the algorithm (and quantum)
python3 xv6-style-scheduler/scheduler_simulator/simulator.py \
  --workload workloads/mixed_workload.json \
  --guard outputs/guard_decision.json \
  --output traces/mixed_guard_selected.jsonl
```
