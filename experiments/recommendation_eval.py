#!/usr/bin/env python3
"""recommendation_eval.py — does retrieval-augmented advice satisfy the two
project goals, measured by leave-one-out cross-validation on the REAL xv6 labels?

Modes evaluated (leave-one-out over the xv6-measured workloads):
  fixed_mlfq / fixed_rr : trivial "always X" baselines (the bar to beat).
  knn                   : no-LLM retrieval classifier (majority measured_best of
                          the k nearest past workloads). Honest reference — shows
                          how much signal is in retrieval ALONE.
  llm_facts             : the current advisor (xv6 facts, NO retrieval).
  llm_retrieval         : advisor + retrieved measured precedents (the proposal).

Goal 1 ("LLM makes the best choice") is met if llm_retrieval beats the best
fixed baseline AND llm_facts. Goal 2 ("evaluate -> feedback -> improve") is met
if accuracy rises with store size (the --learning-curve report) and
llm_retrieval > llm_facts (the accumulated measured feedback helps).

The offline modes (fixed/knn/curve) need no API. The llm_* modes call Solar and
CACHE each response under outputs/learning/llm_cache/ so reruns are free and
deterministic-ish. Run `--offline` to skip the LLM modes entirely.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))           # core pipeline modules
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling experiments/

import outcome_store as osmod  # noqa: E402

LEARN_DIR = PROJECT_ROOT / "outputs" / "learning"


# ── offline predictors ───────────────────────────────────────────────────────
def predict_fixed(algo):
    return lambda rec, store: algo


def predict_knn(k):
    return lambda rec, store: osmod.knn_predict(
        rec["features"], store, k, exclude_name=rec["name"])


# ── evaluation ───────────────────────────────────────────────────────────────
def leave_one_out(store: list[dict], predict, label: str) -> dict:
    """Run leave-one-out; each prediction excludes the held-out workload from the
    store. Returns accuracy + per-item correctness."""
    correct = 0
    items = []
    for rec in store:
        pred = predict(rec, store)
        ok = (pred == rec["measured_best"])
        correct += int(ok)
        items.append({"name": rec["name"], "true": rec["measured_best"],
                      "pred": pred, "ok": ok})
    return {"mode": label, "n": len(store),
            "correct": correct, "accuracy": round(correct / len(store), 3),
            "items": items}


def learning_curve(store: list[dict], k: int, folds: int = 40,
                   seed: int = 42) -> list[dict]:
    """How does no-LLM retrieval accuracy grow as the outcome store fills up?
    For each store size m, hold out each workload and draw `folds` random
    m-subsets of the remaining records to retrieve from; average accuracy.
    Demonstrates Goal 2: more accumulated measured feedback -> better picks."""
    rng = random.Random(seed)
    sizes = list(range(2, len(store)))  # m = 2 .. n-1 available precedents
    curve = []
    for m in sizes:
        acc_accum = 0.0
        trials = 0
        for rec in store:
            others = [r for r in store if r["name"] != rec["name"]]
            if m > len(others):
                continue
            hits = 0
            for _ in range(folds):
                subset = rng.sample(others, m)
                pred = osmod.knn_predict(rec["features"], subset, k)
                hits += int(pred == rec["measured_best"])
            acc_accum += hits / folds
            trials += 1
        curve.append({"store_size": m, "accuracy": round(acc_accum / trials, 3)})
    return curve


def _fmt(report: dict) -> str:
    lines = [f"  {report['mode']:16} {report['accuracy']:.3f} "
             f"({report['correct']}/{report['n']})"]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="xv6-measured",
                    help="expected_best_source filter ('xv6-measured' or 'all')")
    ap.add_argument("--k", type=int, default=3, help="retrieval neighbours")
    ap.add_argument("--offline", action="store_true",
                    help="skip LLM modes (fixed/knn/curve only)")
    ap.add_argument("--reps", type=int, default=1,
                    help="LLM reps per workload (majority vote)")
    ap.add_argument("--out", default=str(LEARN_DIR / "recommendation_eval.json"))
    args = ap.parse_args()

    src = None if args.source == "all" else args.source
    store = osmod.build_store(source_filter=src)
    print(f"[eval] outcome store ({args.source}): {len(store)} records "
          f"({sum(r['measured_best']=='MLFQ' for r in store)} MLFQ / "
          f"{sum(r['measured_best']=='RR' for r in store)} RR / "
          f"{sum(r['measured_best'] not in ('MLFQ','RR') for r in store)} other)\n")

    reports = []
    reports.append(leave_one_out(store, predict_fixed("MLFQ"), "fixed_mlfq"))
    reports.append(leave_one_out(store, predict_fixed("RR"), "fixed_rr"))
    reports.append(leave_one_out(store, predict_knn(args.k), f"knn_k{args.k}"))

    print("OFFLINE modes (leave-one-out accuracy):")
    for r in reports:
        print(_fmt(r))

    curve = learning_curve(store, k=args.k)
    print("\nLEARNING CURVE (no-LLM retrieval, accuracy vs store size):")
    for pt in curve:
        bar = "#" * int(pt["accuracy"] * 40)
        print(f"  m={pt['store_size']:2}  {pt['accuracy']:.3f}  {bar}")

    result = {"source": args.source, "k": args.k, "store_size": len(store),
              "reports": reports, "learning_curve": curve}

    if not args.offline:
        import retrieval_advisor as ra
        for mode in ("llm_facts", "llm_retrieval"):
            use_ret = (mode == "llm_retrieval")
            rep = leave_one_out(
                store,
                lambda rec, st, ur=use_ret: ra.recommend_cached(
                    rec, st, k=args.k, use_retrieval=ur, reps=args.reps),
                mode)
            reports.append(rep)
            print(f"\n{mode} (leave-one-out, reps={args.reps}):")
            print(_fmt(rep))

    LEARN_DIR.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(f"\n[eval] wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
