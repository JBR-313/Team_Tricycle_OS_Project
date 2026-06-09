#!/usr/bin/env python3
"""learning_curve_bank.py — build the measured instance BANK for the
adaptive-learning study (does repeating a workload PATTERN let retrieval-
augmented advice improve, and does a pattern DRIFT degrade it?).

WHY A BANK (cost):
  regret needs every comparison algorithm's measured value on the SAME workload
  (metrics.pick_best_algorithm / compute_regret). The honest backend is real
  xv6, and the simulator was removed. So each distinct instance costs one xv6
  run PER algorithm. We therefore sweep a FINITE bank of (family x jittered
  instance) ONCE here and cache it; the sequence-replay experiment
  (learning_curve_replay.py) then draws from this bank with ZERO further xv6
  runs — repetition and drift are modelled by the REPLAY ORDER, not new sweeps.

COMPARISON SET = the project's 4 non-predictive core algorithms
  (RR / FCFS / Priority+Aging / MLFQ). SJF/SRTF are intentionally excluded: they
  need a burst predictor, and mixing prediction error into "the measured best"
  would confound the learning signal we are trying to isolate. (Sensitivity with
  a heuristic predictor can be added later.)

HONESTY:
  * Custom workloads run on the real kernel via `schedtest --procs` (single CPU
    burst per process, the kernel's only custom-injection shape).
  * Stored features are prompt-safe visible aggregates only (outcome_store.
    prompt_safe_features): no per-process actual_bursts, no total_cpu_work.
  * `measured_best` is the evaluation answer for that instance, used leave-one-
    out by the replay (an instance never retrieves itself).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "experiments"))

import orchestrator as orch                       # noqa: E402
from metrics import compute_metrics, pick_best_algorithm, compute_regret  # noqa: E402
from workload_analyzer import analyze_workload    # noqa: E402
import outcome_store as osmod                      # noqa: E402

OUT_DIR = ROOT / "outputs" / "learning_curve"
RAW_DIR = OUT_DIR / "xv6"
BANK = OUT_DIR / "bank.json"

# Core, non-predictive comparison set (see module docstring).
ALGOS = ("rr", "fcfs", "priority", "mlfq")


# ── workload families ─────────────────────────────────────────────────────────
# Each family is a recurring user PATTERN. Instances are jittered around the
# family centroid so they are "similar but not identical" (a fair test of
# retrieval — a byte-identical repeat would degenerate into a lookup table).
# Every family has a distinct VISIBLE feature fingerprint (process_count,
# arrival gaps, cpu/interactive label ratio, priority spread, target_metric) so
# the families are separable in retrieval space, and a distinct structural
# reason for a different scheduler to win.
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
    rng = random.Random(seed)
    procs, target = FAMILIES[family](rng)
    return {
        "id": f"{family}_s{seed}",
        "family": family,
        "schema_version": 2,
        "target_metric": target,
        "processes": procs,
    }


def _spec(doc: dict) -> str:
    return ",".join(
        f"{p['arrival_time']}:{p['actual_bursts'][0]}:{p['priority']}"
        for p in doc["processes"])


# ── one instance: sweep all comparison algos on real xv6 ──────────────────────
def sweep_instance(doc: dict, dry_run: bool = False) -> dict | None:
    """Run every comparison algorithm on this instance via xv6 --procs, compute
    each one's metrics, then derive best + per-algo regret on the target metric."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    name = doc["id"]
    spec = _spec(doc)
    target = doc["target_metric"]
    all_metrics: dict[str, dict] = {}

    for algo in ALGOS:
        tag = f"{name}_{algo}"
        raw = RAW_DIR / f"{tag}.log"
        if not orch.qemu_run_schedtest(algo, 42, "custom", raw, dry_run,
                                       ["--procs", spec]):
            print(f"  [WARN] {tag}: no RUN_END")
            return None
        if dry_run:
            continue
        trace_name = f"trace_{tag}.jsonl"
        orch.parse_xv6_log(raw, algo.upper(), 42, "custom", RAW_DIR, dry_run,
                           trace_name)
        tp = RAW_DIR / trace_name
        if not tp.is_file():
            print(f"  [WARN] {tag}: no trace")
            return None
        all_metrics[algo.upper()] = compute_metrics(orch._load_jsonl(tp))

    if dry_run:
        return None

    best = pick_best_algorithm(all_metrics, target)
    per_algo_value = {a: m.get(target) for a, m in all_metrics.items()}
    # regret of CHOOSING algo a = its normalised distance from the best on target
    per_algo_regret = {
        a: compute_regret(target, per_algo_value[a], all_metrics)
        for a in all_metrics
    }
    summary = analyze_workload(doc, ROOT / "workloads" / f"{name}.json")
    feats = osmod.prompt_safe_features(summary)
    return {
        "name": name,
        "family": doc["family"],
        "target_metric": target,
        "features": feats,
        "measured_best": best,
        "per_algo_value": per_algo_value,
        "per_algo_regret": per_algo_regret,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instances", type=int, default=5,
                    help="jittered instances per family")
    ap.add_argument("--families", default=",".join(FAMILIES),
                    help="comma-separated family subset")
    ap.add_argument("--base-seed", type=int, default=7000)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the commands without running xv6")
    args = ap.parse_args()

    fams = [f for f in args.families.split(",") if f in FAMILIES]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    records, total, ok = [], 0, 0
    for fi, fam in enumerate(fams):
        for k in range(args.instances):
            seed = args.base_seed + fi * 1000 + k
            doc = build_doc(fam, seed)
            total += 1
            print(f"[bank] {doc['id']}  target={doc['target_metric']}  "
                  f"spec={_spec(doc)}")
            rec = sweep_instance(doc, dry_run=args.dry_run)
            if rec is None:
                if not args.dry_run:
                    print(f"  [SKIP] {doc['id']} (sweep failed)")
                continue
            ok += 1
            print(f"  -> best={rec['measured_best']}  "
                  f"values={rec['per_algo_value']}")
            records.append(rec)

    if args.dry_run:
        print(f"\n[bank] DRY-RUN: would sweep {total} instances "
              f"x {len(ALGOS)} algos = {total * len(ALGOS)} xv6 runs")
        return 0

    # within-family winner stability (a clean PATTERN must keep a stable winner)
    from collections import Counter
    print("\n[bank] within-family measured_best distribution:")
    for fam in fams:
        dist = Counter(r["measured_best"] for r in records if r["family"] == fam)
        print(f"  {fam:12} {dict(dist)}")

    BANK.write_text(json.dumps(
        {"algos": list(ALGOS), "families": fams,
         "instances_per_family": args.instances, "records": records},
        indent=2) + "\n")
    print(f"\n[bank] {ok}/{total} instances swept -> {BANK}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
