#!/usr/bin/env python3
"""workload_gen.py — random workload generator for the leak-free burst-prediction
study (docs/GOAL_burst_eval.md).

THE MAKE-OR-BREAK RULE: the actual CPU burst is a NOISY function of a HIDDEN
per-process `type`, and the visible feature that signals the type (`io_count`) is
an IMPERFECT signal of it. We never write a deterministic feature->burst map (that
would just relocate the old `description` leak into the generator). The hidden
type and the actual burst are used to GENERATE and SCORE only — never put in a
prompt (same contract as `actual_bursts`).

Two regimes:
  - SIGNAL  : io_count is graded by type (more I/O -> shorter burst), with noise.
              A graded predictor (the LLM) can order short<med<long; the binary
              heuristic (io>0 -> short) cannot separate med from long; blind EMA
              cannot order at all. So there is real, leak-free signal to win on.
  - CONTROL : burst is drawn independently of io_count. NO predictor should beat
              blind EMA here. This is the built-in leak detector: if the LLM
              "wins" on CONTROL, something leaks.

Single CPU burst per process (one-shot, like the xv6 `prio_starve` profile): the
study is about COLD-START ordering, which is what the first-burst prior drives.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

# Hidden types -> (burst range). Noisy: the burst is sampled uniformly in-range,
# the ranges overlap slightly at the edges via the noise term below.
TYPE_BURST = {
    "short":  (1, 4),
    "medium": (8, 14),
    "long":   (20, 30),
}
# io_count a process of each type TENDS to show (the imperfect signal).
TYPE_IO = {
    "short":  (3, 4),
    "medium": (1, 2),
    "long":   (0, 0),
}
# priority a process of each type TENDS to show (second, INDEPENDENT noisy
# signal, used only in multi-feature mode). xv6: lower number = higher priority,
# so interactive/short jobs get low numbers. Each feature alone is weak; the
# COMBINATION is what carries the signal — that is the point of multi mode.
TYPE_PRI = {
    "short":  (1, 3),
    "medium": (4, 6),
    "long":   (7, 9),
}
TYPES = ("short", "medium", "long")
FEATURE_NOISE = 0.25   # single mode: P(io_count drawn from a RANDOM type)
MF_NOISE = 0.40        # multi mode: per-feature P(drawn from a RANDOM type) —
                       # higher, so NO single feature is reliable; only fusing
                       # io_count + priority recovers the type well.


def _burst_for(rng: random.Random, t: str) -> int:
    lo, hi = TYPE_BURST[t]
    return rng.randint(lo, hi)


def _noisy_feature(rng: random.Random, t: str, table: dict, noise: float) -> int:
    # Imperfect signal: with prob `noise` the feature reflects a DIFFERENT
    # (random) type, so the feature->type link is real but not deterministic.
    src = rng.choice(TYPES) if rng.random() < noise else t
    lo, hi = table[src]
    return rng.randint(lo, hi)


def _io_for(rng: random.Random, t: str) -> int:
    return _noisy_feature(rng, t, TYPE_IO, FEATURE_NOISE)


def generate_workload(seed: int, n: int = 6, control: bool = False,
                      multi: bool = False) -> dict:
    """Return one v2 workload dict. `actual_bursts` and the hidden `_type` are
    ground truth (evaluator-only); io_count/arrival/priority are visible.

    multi=False: single-feature signal (io_count only).
    multi=True : two INDEPENDENT noisy signals (io_count AND priority), each
                 unreliable alone — a single-feature heuristic is weak, only
                 fusing both recovers the type. This is the setup that tests
                 whether the LLM's reasoning beats a FAIR multi-feature rule.
    """
    rng = random.Random(seed if not control else seed ^ 0x5EED)
    procs = []
    arrival = 0
    for i in range(n):
        t = rng.choice(TYPES)
        if control:
            # burst independent of any visible feature; features also independent.
            burst = rng.randint(1, 30)
            io_count = rng.randint(0, 4)
            priority = rng.randint(1, 9)
        elif multi:
            burst = _burst_for(rng, t)
            io_count = _noisy_feature(rng, t, TYPE_IO, MF_NOISE)
            priority = _noisy_feature(rng, t, TYPE_PRI, MF_NOISE)
        else:
            burst = _burst_for(rng, t)
            io_count = _io_for(rng, t)
            priority = rng.randint(1, 9)
        procs.append({
            "pid": i + 1,
            "arrival_time": arrival,
            "priority": priority,
            # single CPU burst actually executed + scored (ground truth):
            "cpu_bursts": [burst],
            "actual_bursts": [burst],
            # io_bursts is the VISIBLE signal — only its COUNT is a feature; the
            # values are placeholders and are never executed by the xv6 harness.
            "io_bursts": [1] * io_count,
            # hidden ground-truth type, evaluator-only (NOT a visible feature;
            # analyze_workload does not surface it and the prompt never sees it).
            "_type": t if not control else "control",
        })
        arrival += rng.randint(1, 3)   # staggered arrivals so SRTF preemption matters
    return {
        "schema_version": 2,
        "target_metric": "avg_waiting_time",
        # NOTE: deliberately NO `description` / `id` / per-process `label` — those
        # are the answer-key channels we are closing. The advisor prompt also
        # strips them defensively (tools/llm_advisor.py _PROMPT_STRIP_KEYS).
        "processes": procs,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="outputs/random_eval/workloads")
    ap.add_argument("--n-signal", type=int, default=10)
    ap.add_argument("--n-control", type=int, default=6)
    ap.add_argument("--procs", type=int, default=6, help="processes per workload")
    ap.add_argument("--base-seed", type=int, default=1000)
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for k in range(args.n_signal):
        d = generate_workload(args.base_seed + k, args.procs, control=False)
        p = out / f"sig_{k:03d}.json"
        p.write_text(json.dumps(d, indent=2) + "\n")
        written.append(str(p))
    for k in range(args.n_control):
        d = generate_workload(args.base_seed + 5000 + k, args.procs, control=True)
        p = out / f"ctl_{k:03d}.json"
        p.write_text(json.dumps(d, indent=2) + "\n")
        written.append(str(p))
    print(f"[gen] wrote {len(written)} workloads to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
