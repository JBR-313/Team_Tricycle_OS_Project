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
# The recurring-PATTERN generator now lives in the shared, dependency-free
# experiments/workload_families.py (single source of truth, also used by the
# orchestrator's --random-family live mode). Re-exported here so the rest of this
# module (and any importer of learning_curve_bank) keeps working unchanged.
from workload_families import (                    # noqa: E402
    FAMILIES, build_doc, spec as _spec,
    gen_interactive, gen_cpu_batch, gen_convoy, gen_priority,
)


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
