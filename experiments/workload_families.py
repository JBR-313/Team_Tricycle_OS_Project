#!/usr/bin/env python3
"""workload_families.py — the canonical recurring-workload PATTERN generator.

A "family" is a recurring user workload PATTERN (the project premise: in one
local environment a user runs many SIMILAR-but-not-identical workloads). Each
family draws jittered instances around a centroid: same visible fingerprint,
different exact numbers, so retrieval over accumulated outcomes can warm-start a
recommendation without degenerating into a byte-for-byte lookup table.

Single source of truth shared by:
  * experiments/learning_curve_bank.py — the measured adaptive-learning study
  * scripts/orchestrator.py            — the `--random-family` live pipeline mode

HONESTY: this module only GENERATES workloads. `actual_bursts` is the real CPU
burst the kernel will execute via `schedtest --procs`; it is never placed in an
advise prompt (the advisor strips per-process bursts, `label`, and the top-level
`family`/`id` answer-tags — see tools/llm_advisor.py). The generator has NO
dependency on the orchestrator or the kernel, so it imports cleanly from either.

Each family has a distinct VISIBLE feature fingerprint (process_count, arrival
gaps, cpu/interactive label ratio, priority spread, target_metric) so the
families are separable in retrieval space, and a distinct structural reason for a
different scheduler to win.
"""
from __future__ import annotations

import random


def _proc(pid, arrival, burst, prio, label):
    b = max(1, int(round(burst)))
    return {"pid": pid, "arrival_time": max(0, int(arrival)),
            "cpu_bursts": [b], "actual_bursts": [b], "io_bursts": [],
            "priority": int(prio), "label": label}


def gen_interactive(rng):
    """Many short interactive jobs, staggered arrivals, uniform priority.
    Response-time target — RR/MLFQ should shine (fairness/low first-response)."""
    n = rng.choice([6, 7, 8])
    procs = []
    for i in range(n):
        procs.append(_proc(i + 1, arrival=i + rng.randint(0, 1),
                            burst=rng.randint(2, 4), prio=5, label="interactive"))
    return procs, "avg_response_time"


def gen_cpu_batch(rng):
    """A few long CPU-bound jobs, all present at t=0, uniform priority.
    Turnaround target — shortest-remaining ordering matters; among the 4 core
    algos this tends to separate MLFQ/RR from FCFS (convoy-on-arrival-order)."""
    n = rng.choice([4, 5])
    procs = []
    for i in range(n):
        procs.append(_proc(i + 1, arrival=0,
                            burst=rng.randint(10, 18), prio=5, label="cpu_bound"))
    return procs, "avg_turnaround_time"


def gen_convoy(rng):
    """One long CPU hog arrives first, then a burst of short interactive jobs.
    Waiting target — the classic convoy: FCFS makes the shorts wait behind the
    hog; preemptive/aging algos (MLFQ) relieve it."""
    procs = [_proc(1, arrival=0, burst=rng.randint(16, 22), prio=5, label="cpu_bound")]
    n_short = rng.choice([4, 5])
    for i in range(n_short):
        procs.append(_proc(i + 2, arrival=1 + rng.randint(0, 2),
                            burst=rng.randint(2, 4), prio=5, label="interactive"))
    return procs, "avg_waiting_time"


def gen_priority(rng):
    """Wide priority spread, medium bursts, simultaneous arrival.
    Waiting target with a strong priority signal — Priority+Aging / MLFQ should
    beat plain RR/FCFS that ignore the priority field."""
    n = rng.choice([5, 6])
    procs = []
    for i in range(n):
        procs.append(_proc(i + 1, arrival=0, burst=rng.randint(5, 10),
                            prio=rng.choice([1, 2, 3, 7, 8, 9]), label="mixed"))
    return procs, "avg_waiting_time"


FAMILIES = {
    "interactive": gen_interactive,
    "cpu_batch":   gen_cpu_batch,
    "convoy":      gen_convoy,
    "priority":    gen_priority,
}


def build_doc(family: str, seed: int) -> dict:
    """Generate one jittered v2 workload instance of `family` (deterministic in
    `seed`: same (family, seed) always yields the identical instance)."""
    rng = random.Random(seed)
    procs, target = FAMILIES[family](rng)
    return {
        "id": f"{family}_s{seed}",
        "family": family,
        "schema_version": 2,
        "target_metric": target,
        "processes": procs,
    }


def spec(doc: dict) -> str:
    """The kernel `schedtest --procs` injection string for a generated doc:
    "arrival:burst:prio,arrival:burst:prio,..." in fork order."""
    return ",".join(
        f"{p['arrival_time']}:{p['actual_bursts'][0]}:{p['priority']}"
        for p in doc["processes"])
