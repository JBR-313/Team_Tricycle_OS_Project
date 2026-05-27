#!/usr/bin/env python3
"""Host-side scheduler simulator (v1) for the Team Tricycle OS project.

Scheduler Engine / Trace Collector (host-side fallback).

This tool reads a workload JSON (single-burst ``cpu_burst`` or repo-wide
``cpu_bursts`` multi-burst schema), optionally reads a guard decision JSON,
runs ONE scheduling algorithm, and writes a JSONL trace.

It is purely host-side: it does not touch xv6 source, call any LLM, compute
metrics, or render a dashboard.

Supported algorithms: RR, FCFS, SJF, PRIORITY.
MLFQ / SRTF / I/O sleep+wakeup / xv6 hooks are intentionally NOT implemented
in v1; an unsupported requested algorithm falls back (warning to stderr).

The simulator is deterministic: given the same workload and arguments it
always produces byte-identical traces. All tie-breaks are fully specified.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

SUPPORTED_ALGORITHMS = ("RR", "FCFS", "SJF", "PRIORITY")

# Algorithms we recognise by name but deliberately do not implement in v1.
KNOWN_UNIMPLEMENTED = ("MLFQ", "SRTF")

DEFAULT_ALGORITHM = "RR"
DEFAULT_QUANTUM = 10
DEFAULT_STARVATION_THRESHOLD = 20
DEFAULT_PRIORITY = 10

# Trace event names.
EV_ARRIVE = "ARRIVE"
EV_DISPATCH = "DISPATCH"
EV_PREEMPT = "PREEMPT"
EV_EXIT = "EXIT"
EV_IDLE = "IDLE"
EV_STARVATION = "STARVATION_WARNING"

# Trace state names.
ST_RUNNABLE = "RUNNABLE"
ST_RUNNING = "RUNNING"
ST_ZOMBIE = "ZOMBIE"
ST_IDLE = "IDLE"


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #

class WorkloadError(Exception):
    """Raised when a workload file fails validation."""


class GuardError(Exception):
    """Raised when a guard decision file cannot be parsed."""


def warn(message: str) -> None:
    """Print a warning to stderr (kept out of the trace / stdout summary)."""
    print(f"[simulator] WARNING: {message}", file=sys.stderr)


# --------------------------------------------------------------------------- #
# Process model
# --------------------------------------------------------------------------- #

@dataclass
class Process:
    """A single workload process plus the runtime state the engine mutates."""

    pid: object                       # int or str; preserved verbatim in trace
    arrival_time: int
    total_cpu_burst: int              # total CPU work for this process
    priority: int = DEFAULT_PRIORITY
    ptype: Optional[str] = None       # original "type" or "label" value

    remaining: int = field(init=False)
    ready_since: int = field(default=-1, init=False)
    warned: bool = field(default=False, init=False)
    arrived: bool = field(default=False, init=False)
    first_run_time: Optional[int] = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.remaining = self.total_cpu_burst


def pid_sort_key(pid: object) -> tuple:
    """Deterministic ordering for pids that may be int or str.

    Integer pids sort numerically and ahead of string pids; string pids sort
    lexicographically.
    """
    if isinstance(pid, int) and not isinstance(pid, bool):
        return (0, pid, "")
    return (1, 0, str(pid))


# --------------------------------------------------------------------------- #
# Workload loading + validation
# --------------------------------------------------------------------------- #

def _resolve_burst(item: dict, label: str, errors: List[str]) -> Optional[int]:
    """Resolve the total CPU burst from either cpu_burst or cpu_bursts.

    - If ``cpu_burst`` is present, use it directly.
    - Otherwise, if ``cpu_bursts`` is a non-empty list of positive ints, use
      sum(cpu_bursts) as the v1 total (multi-burst is flattened in v1).
    - On any problem, append a message to ``errors`` and return None.
    """
    has_single = "cpu_burst" in item
    has_multi = "cpu_bursts" in item

    if has_single:
        try:
            burst = int(item["cpu_burst"])
        except (TypeError, ValueError):
            errors.append(f"{label}: cpu_burst must be an integer")
            return None
        if burst <= 0:
            errors.append(f"{label}: cpu_burst must be > 0 (got {burst})")
            return None
        return burst

    if has_multi:
        bursts = item["cpu_bursts"]
        if not isinstance(bursts, list) or not bursts:
            errors.append(
                f"{label}: cpu_bursts must be a non-empty list of positive integers"
            )
            return None
        total = 0
        for b in bursts:
            try:
                bi = int(b)
            except (TypeError, ValueError):
                errors.append(
                    f"{label}: cpu_bursts entries must be integers (got {b!r})"
                )
                return None
            if bi <= 0:
                errors.append(
                    f"{label}: cpu_bursts entries must be > 0 (got {bi})"
                )
                return None
            total += bi
        return total

    errors.append(f"{label}: missing required field 'cpu_burst' or 'cpu_bursts'")
    return None


def load_workload(path: Path) -> List[Process]:
    """Load and validate a workload file. Raises WorkloadError on any problem.

    Validation is fully completed before the simulation runs, so a bad workload
    never results in a partial trace being written.
    """
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        raise WorkloadError(f"workload file not found: {path}")
    except json.JSONDecodeError as exc:
        raise WorkloadError(f"workload is not valid JSON ({path}): {exc}")

    if not isinstance(raw, list):
        raise WorkloadError(
            f"workload must be a JSON array, got {type(raw).__name__}. "
            "Each entry is a process object."
        )

    errors: List[str] = []
    processes: List[Process] = []

    for idx, item in enumerate(raw):
        where = f"entry {idx}"
        if not isinstance(item, dict):
            errors.append(f"{where}: must be a JSON object")
            continue

        missing = [k for k in ("pid", "arrival_time") if k not in item]
        if missing:
            errors.append(f"{where}: missing required field(s): {', '.join(missing)}")
            continue

        pid = item["pid"]
        label = f"pid {pid!r}"

        try:
            arrival = int(item["arrival_time"])
        except (TypeError, ValueError):
            errors.append(f"{label}: arrival_time must be an integer")
            continue
        if arrival < 0:
            errors.append(f"{label}: arrival_time must be >= 0 (got {arrival})")

        burst = _resolve_burst(item, label, errors)
        if burst is None:
            continue

        # io_bursts is accepted (and lightly validated) but not simulated in v1.
        if "io_bursts" in item and not isinstance(item["io_bursts"], list):
            errors.append(f"{label}: io_bursts must be a list if present")
            continue

        priority = item.get("priority", DEFAULT_PRIORITY)
        try:
            priority = int(priority)
        except (TypeError, ValueError):
            errors.append(f"{label}: priority must be an integer if present")
            continue

        # "label" is the project-wide schema name; "type" is the v1.5 alias.
        ptype = item.get("type", item.get("label"))
        processes.append(Process(pid, arrival, burst, priority, ptype))

    if errors:
        raise WorkloadError(
            "invalid workload:\n  - " + "\n  - ".join(errors)
        )
    if not processes:
        raise WorkloadError("workload is empty (no processes)")

    return processes


# --------------------------------------------------------------------------- #
# Guard decision parsing
# --------------------------------------------------------------------------- #

def load_guard(path: Path) -> dict:
    """Load a guard decision JSON object. Raises GuardError on problems."""
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        raise GuardError(f"guard file not found: {path}")
    except json.JSONDecodeError as exc:
        raise GuardError(f"guard is not valid JSON ({path}): {exc}")
    if not isinstance(data, dict):
        raise GuardError("guard decision must be a JSON object")
    return data


# Algorithm-name keys the guard may use, in resolution priority order.
_GUARD_ALGO_KEYS = (
    "algorithm",
    "scheduling_algorithm",
    "recommended_scheduling_algorithm",
    "selected_algorithm",
    "fallback_algorithm",
    "fallback_scheduling_algorithm",
)

_GUARD_FALLBACK_KEYS = ("fallback_algorithm", "fallback_scheduling_algorithm")


def resolve_algorithm(cli_algorithm: Optional[str], guard: Optional[dict]) -> str:
    """Apply the algorithm selection precedence and return an UPPER-CASE name.

    Precedence:
        1. explicit --algorithm
        2. guard.algorithm
        3. guard.scheduling_algorithm
        4. guard.recommended_scheduling_algorithm
        5. guard.selected_algorithm
        6. guard.fallback_algorithm
        7. guard.fallback_scheduling_algorithm
        8. RR
    """
    if cli_algorithm:
        return str(cli_algorithm).strip().upper()
    if guard:
        for key in _GUARD_ALGO_KEYS:
            cand = guard.get(key)
            if cand:
                return str(cand).strip().upper()
    return DEFAULT_ALGORITHM


def _guard_fallback(guard: Optional[dict]) -> Optional[str]:
    if not guard:
        return None
    for key in _GUARD_FALLBACK_KEYS:
        cand = guard.get(key)
        if cand:
            return str(cand).strip().upper()
    return None


def coerce_supported(algorithm: str, guard: Optional[dict]) -> str:
    """Map a requested algorithm onto something v1 can actually run.

    If the requested algorithm is unsupported (e.g. MLFQ/SRTF), prefer the
    guard's fallback algorithm when supported, otherwise fall back to RR.
    Every substitution is reported on stderr.
    """
    if algorithm in SUPPORTED_ALGORITHMS:
        return algorithm

    if algorithm in KNOWN_UNIMPLEMENTED:
        warn(f"algorithm '{algorithm}' is not implemented in v1.")
    else:
        warn(f"algorithm '{algorithm}' is unknown.")

    fallback = _guard_fallback(guard)
    if fallback and fallback in SUPPORTED_ALGORITHMS and fallback != algorithm:
        warn(f"using guard fallback '{fallback}'.")
        return fallback

    warn(f"falling back to {DEFAULT_ALGORITHM}.")
    return DEFAULT_ALGORITHM


def resolve_quantum(cli_quantum: Optional[int], guard: Optional[dict]) -> int:
    """Resolve the RR time quantum.

    Precedence:
        1. --quantum
        2. guard.params.quantum
        3. guard.parameters.time_quantum
        4. DEFAULT_QUANTUM (10)
    """
    if cli_quantum is not None:
        return cli_quantum
    if guard:
        params = guard.get("params")
        if isinstance(params, dict) and params.get("quantum") is not None:
            q = params["quantum"]
            # Some guard schemas pass a list (MLFQ); take the first entry.
            if isinstance(q, list) and q:
                q = q[0]
            return int(q)
        parameters = guard.get("parameters")
        if isinstance(parameters, dict) and parameters.get("time_quantum") is not None:
            return int(parameters["time_quantum"])
    return DEFAULT_QUANTUM


# --------------------------------------------------------------------------- #
# Scheduling engine
# --------------------------------------------------------------------------- #

def _selection_key(algorithm: str) -> Optional[Callable[[Process], tuple]]:
    """Return the min() sort key for a non-preemptive picker, or None for RR."""
    if algorithm == "FCFS":
        return lambda p: (p.arrival_time, pid_sort_key(p.pid))
    if algorithm == "SJF":
        return lambda p: (p.remaining, p.arrival_time, pid_sort_key(p.pid))
    if algorithm == "PRIORITY":
        return lambda p: (p.priority, p.arrival_time, pid_sort_key(p.pid))
    return None  # RR uses simple FIFO


def simulate(
    processes: List[Process],
    algorithm: str,
    quantum: int,
    starvation_threshold: int,
) -> List[dict]:
    """Run one algorithm and return the trace as a list of JSON-ready dicts.

    RR is preemptive (time-sliced by ``quantum``); FCFS/SJF/PRIORITY are
    non-preemptive in v1. The whole trace is buffered and returned so the
    caller can write it in one shot (no partial files on error).

    Every record carries primary keys ``tick``/``algo`` plus legacy aliases
    ``time``/``algorithm`` for backward compatibility with v1.5 consumers.
    """
    trace: List[dict] = []

    def emit(tick: int, event: str, pid: object, state: Optional[str], **extra) -> None:
        record = {
            "tick": tick,
            "algo": algorithm,
            "event": event,
            "pid": pid,
            "state": state,
            # Backward-compat aliases (v1.5 schema).
            "time": tick,
            "algorithm": algorithm,
        }
        record.update(extra)
        trace.append(record)

    pending = sorted(processes, key=lambda p: (p.arrival_time, pid_sort_key(p.pid)))
    ready: List[Process] = []

    def admit(tick: int) -> None:
        # Idempotent: admits every not-yet-arrived process whose arrival time
        # has been reached. Safe to call repeatedly at the same tick.
        for proc in pending:
            if not proc.arrived and proc.arrival_time <= tick:
                proc.arrived = True
                proc.ready_since = tick
                proc.warned = False
                ready.append(proc)
                emit(
                    tick, EV_ARRIVE, proc.pid, ST_RUNNABLE,
                    queue=0,
                    priority=proc.priority,
                    burst_hint=None,
                )

    def check_starvation(tick: int, dispatched: Process) -> None:
        if starvation_threshold <= 0:
            return
        for proc in ready:
            if proc is dispatched:
                continue
            wait = tick - proc.ready_since
            if wait >= starvation_threshold and not proc.warned:
                severity = "high" if wait >= starvation_threshold * 2 else "medium"
                emit(
                    tick, EV_STARVATION, proc.pid, ST_RUNNABLE,
                    waiting_since_tick=proc.ready_since,
                    current_waiting_time=wait,
                    wait_time=wait,            # backward-compat alias
                    threshold=starvation_threshold,
                    severity=severity,
                )
                proc.warned = True

    select_key = _selection_key(algorithm)
    total = len(processes)
    finished = 0
    tick = 0
    running: Optional[Process] = None
    quantum_left = 0

    admit(tick)

    while finished < total:
        if running is None:
            if not ready:
                # CPU idle: jump forward to the next arrival.
                upcoming = [p.arrival_time for p in pending if not p.arrived]
                if not upcoming:
                    break  # safety; should not happen while finished < total
                emit(tick, EV_IDLE, None, ST_IDLE)
                tick = min(upcoming)
                admit(tick)
                continue

            # Pick the next process (without removing it yet) so the starvation
            # check can see who is being passed over.
            if select_key is None:  # RR: FIFO
                index = 0
            else:
                index = min(range(len(ready)), key=lambda i: select_key(ready[i]))
            candidate = ready[index]
            check_starvation(tick, dispatched=candidate)

            ready.pop(index)
            running = candidate
            running.warned = False
            if running.first_run_time is None:
                running.first_run_time = tick
            quantum_left = quantum          # only consulted for RR
            emit(tick, EV_DISPATCH, running.pid, ST_RUNNING, queue=0)

        # Execute exactly one tick.
        running.remaining -= 1
        tick += 1
        quantum_left -= 1

        # Admit arrivals at the new tick before re-queuing any preempted
        # process, so freshly-arrived processes sit ahead of it (standard RR).
        admit(tick)

        if running.remaining == 0:
            arrival = running.arrival_time
            first_run = running.first_run_time if running.first_run_time is not None else tick
            turnaround = tick - arrival
            response = first_run - arrival
            waiting = turnaround - running.total_cpu_burst
            emit(
                tick, EV_EXIT, running.pid, ST_ZOMBIE,
                queue=0,
                turnaround=turnaround,
                waiting=waiting,
                response=response,
            )
            running = None
            finished += 1
        elif algorithm == "RR" and quantum_left == 0:
            emit(
                tick, EV_PREEMPT, running.pid, ST_RUNNABLE,
                queue=0,
                reason="quantum_expired",
            )
            running.ready_since = tick
            running.warned = False
            ready.append(running)           # preempted -> back of the queue
            running = None
        # otherwise the same process keeps running next tick

    return trace


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

def write_trace(trace: List[dict], output_path: Path) -> None:
    """Write the buffered trace as JSONL, creating the directory if needed."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as fh:
        for record in trace:
            fh.write(json.dumps(record) + "\n")


def default_output_path(workload_path: Path, algorithm: str) -> Path:
    """traces/<workload_stem>_<algorithm>.jsonl relative to the current dir."""
    return Path("traces") / f"{workload_path.stem}_{algorithm.lower()}.jsonl"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="simulator.py",
        description="Host-side scheduler simulator v1 (RR/FCFS/SJF/PRIORITY).",
    )
    parser.add_argument(
        "--workload", required=True,
        help="path to a workload JSON array (cpu_burst or cpu_bursts schema)",
    )
    parser.add_argument(
        "--algorithm",
        help="RR | FCFS | SJF | PRIORITY (case-insensitive). "
             "Overrides the guard decision.",
    )
    parser.add_argument(
        "--guard",
        help="path to a guard_decision.json (supports current and legacy schemas)",
    )
    parser.add_argument(
        "--output",
        help="output trace path (.jsonl). Default: traces/<workload>_<algo>.jsonl",
    )
    parser.add_argument(
        "--quantum", type=int,
        help=f"RR time quantum (RR only). Default: {DEFAULT_QUANTUM}",
    )
    parser.add_argument(
        "--starvation-threshold", type=int, default=DEFAULT_STARVATION_THRESHOLD,
        dest="starvation_threshold",
        help=f"emit STARVATION_WARNING after this many waiting ticks. "
             f"Default: {DEFAULT_STARVATION_THRESHOLD}. Use 0 (or negative) to disable.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    workload_path = Path(args.workload)

    try:
        processes = load_workload(workload_path)
    except WorkloadError as exc:
        print(f"[simulator] ERROR: {exc}", file=sys.stderr)
        return 1

    guard: Optional[dict] = None
    if args.guard:
        try:
            guard = load_guard(Path(args.guard))
        except GuardError as exc:
            print(f"[simulator] ERROR: {exc}", file=sys.stderr)
            return 1

    cli_algorithm = args.algorithm.strip().upper() if args.algorithm else None
    requested = resolve_algorithm(cli_algorithm, guard)
    algorithm = coerce_supported(requested, guard)

    quantum = resolve_quantum(args.quantum, guard)
    if quantum <= 0:
        warn(f"quantum must be > 0; using default {DEFAULT_QUANTUM}.")
        quantum = DEFAULT_QUANTUM

    threshold = args.starvation_threshold

    output_path = (
        Path(args.output) if args.output
        else default_output_path(workload_path, algorithm)
    )

    trace = simulate(processes, algorithm, quantum, threshold)
    write_trace(trace, output_path)

    warnings = sum(1 for r in trace if r["event"] == EV_STARVATION)
    print(f"workload   : {workload_path}  ({len(processes)} processes)")
    print(f"algorithm  : {algorithm}" + (f"  (quantum={quantum})" if algorithm == "RR" else ""))
    print(f"starvation : threshold={threshold if threshold > 0 else 'disabled'}, warnings={warnings}")
    print(f"trace      : {output_path}  ({len(trace)} events)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
