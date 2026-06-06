#!/usr/bin/env python3
"""Seed-driven workload jitter — makes `--seed` MEANINGFUL on the simulator.

The curated workloads have fixed arrival times and burst lengths, so without
this every seed produced an identical run. This module derives a distinct but
structurally-equivalent *instance* of a workload from a seed:

  - arrival_time : nudged by ±ARRIVAL_JITTER ticks (clamped to >= 0)
  - cpu/actual/io bursts : scaled by a per-burst factor in
    [1-BURST_JITTER, 1+BURST_JITTER] (rounded, clamped to >= 1)

What is deliberately PRESERVED so the workload keeps its character (and its
`label`, `target_metric`, expected-best hint stay meaningful):
  - the number of processes, and per-process burst/io COUNTS
  - pid, priority, label, and all metadata

`actual_bursts` and `cpu_bursts` are kept as mirrors of each other (the v2
schema invariant): the same jittered list is written to both, so the ground
truth the evaluator reads matches what the simulator executes.

Determinism: same (workload, seed) -> identical output; different seeds ->
different instances. This is what lets you run a workload across several seeds
and report mean ± spread instead of a single point.

xv6 is intentionally NOT jittered here: schedtest.c hardcodes its curated
tables in C with no PRNG, so the kernel backend stays deterministic-by-profile.
The orchestrator only materialises a jittered instance for the simulator
backend.

Usage:
    python3 tools/workload_jitter.py --in workloads/ambiguous_mixed.json \
        --out outputs/workload_instance.json --seed 7
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ARRIVAL_JITTER = 2      # ± ticks on arrival_time
BURST_JITTER = 0.25     # ± fraction on each burst length


def _jitter_bursts(bursts: list, rng: random.Random) -> list:
    out = []
    for b in bursts:
        try:
            base = float(b)
        except (TypeError, ValueError):
            out.append(b)
            continue
        factor = rng.uniform(1.0 - BURST_JITTER, 1.0 + BURST_JITTER)
        out.append(max(1, round(base * factor)))
    return out


def _jitter_process(p: dict, rng: random.Random) -> dict:
    q = dict(p)
    if isinstance(q.get("arrival_time"), (int, float)):
        q["arrival_time"] = max(0, int(q["arrival_time"]) + rng.randint(
            -ARRIVAL_JITTER, ARRIVAL_JITTER))

    # CPU bursts: jitter once, then mirror to both schema keys so actual_bursts
    # (ground truth) and cpu_bursts (legacy mirror) never disagree.
    base = q.get("actual_bursts")
    if not isinstance(base, list):
        base = q.get("cpu_bursts")
    if isinstance(base, list):
        jittered = _jitter_bursts(base, rng)
        if "actual_bursts" in q:
            q["actual_bursts"] = list(jittered)
        if "cpu_bursts" in q:
            q["cpu_bursts"] = list(jittered)

    if isinstance(q.get("io_bursts"), list):
        q["io_bursts"] = _jitter_bursts(q["io_bursts"], rng)
    return q


def jitter_workload(workload, seed: int):
    """Return a seed-jittered copy of a workload (dict with `processes`, or a
    bare list of processes). Structure and counts are preserved."""
    rng = random.Random(seed)

    if isinstance(workload, list):
        return [_jitter_process(p, rng) if isinstance(p, dict) else p
                for p in workload]

    if not isinstance(workload, dict):
        return workload

    out = dict(workload)
    procs = out.get("processes")
    if isinstance(procs, list):
        out["processes"] = [
            _jitter_process(p, rng) if isinstance(p, dict) else p
            for p in procs
        ]
    # Provenance marker (harmless; ignored by the analyzer's known keys).
    out["jittered_from_seed"] = int(seed)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed-jitter a workload instance")
    ap.add_argument("--in", dest="in_path", required=True)
    ap.add_argument("--out", dest="out_path", required=True)
    ap.add_argument("--seed", type=int, required=True)
    args = ap.parse_args()

    src = Path(args.in_path)
    if not src.is_file():
        print(f"[jitter] input not found: {src}", file=sys.stderr)
        return 1
    workload = json.loads(src.read_text(encoding="utf-8"))
    out = jitter_workload(workload, args.seed)

    dst = Path(args.out_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[jitter] seed={args.seed}: {src.name} -> {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
