#!/usr/bin/env python3
"""learning_curve_replay.py — OFFLINE replay over the measured bank: does
repeating a workload PATTERN let retrieval-augmented advice improve (regret
falls), and does a pattern DRIFT degrade it (regret spikes) unless detected?

Runs entirely on outputs/learning_curve/bank.json — ZERO xv6 runs. Repetition
and drift are modelled by the ORDER in which bank instances are replayed, so
the same measured instances yield both the "repeating pattern" sequence and its
negative control just by reordering.

ARMS (y-axis = realised regret of the CHOSEN algorithm on the instance's target
metric; 0 = matched the measured best):
  fixed_rr / fixed_mlfq : no-learning bars (the project's RR baseline + the
                          strongest "always X"). The bar cumulative learning
                          must beat to claim a real effect.
  knn        (Arm B)    : cumulative retrieval — predict the measured best of
                          the k most similar PAST instances seen so far. The
                          store grows online; an instance never sees itself.
  knn_drift  (Arm C)    : Arm B + novelty detection. When the query's nearest
                          neighbour is far (feature drift), the stale store is
                          distrusted and the most-robust-so-far algorithm is
                          used instead — recovering faster after a pattern change.

SEQUENCES:
  stable_blocks : all of family A, then all of B, ... Repetition WITHIN a block
                  (the user's "same pattern daily"); a DRIFT at each boundary.
                  Cumulative learning should show falling regret within a block
                  and a spike at each boundary.
  round_robin   : A,B,C,D,A,B,... consecutive steps are DIFFERENT families — a
                  high-churn stress test for the drift arm (NOT the negative
                  control; knn is order-insensitive, so it still classifies well).

THE INTUITION TEST (order-independent): regret binned by how many SAME-FAMILY
  precedents are already in the store (`precedent_curve`). 0 precedents = the
  cold / just-drifted state; if regret falls as same-family precedents accumulate,
  then "having seen this PATTERN before" is what helps — exactly the claim.

NEGATIVE CONTROL (signal vs artifact): `label_shuffle` permutes the stored
  measured_best labels, destroying the feature->winner relationship. If knn's
  edge over the fixed bar survives shuffling, the edge was an artifact, not
  learned signal. It must COLLAPSE toward the fixed bar.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tools"))

import outcome_store as osmod  # noqa: E402

OUT_DIR = ROOT / "outputs" / "learning_curve"
BANK = OUT_DIR / "bank.json"
RESULTS = OUT_DIR / "results.json"
REPORT = OUT_DIR / "RESULTS.md"

MAX_REGRET = 1.0  # fallback when a chosen algo has no regret value (shouldn't happen)


def load_bank() -> dict:
    return json.loads(BANK.read_text())


def regret_of(rec: dict, algo: str | None) -> float:
    if algo is None:
        return MAX_REGRET
    r = rec["per_algo_regret"].get(algo)
    return MAX_REGRET if r is None else float(r)


# ── predictors ────────────────────────────────────────────────────────────────
def robust_default(store: list[dict]) -> str:
    """Most-robust 'always X' over the store SEEN SO FAR: the algo with the
    lowest mean regret. This is the honest safety-net prior — exactly what a
    learner should fall back to when it has no relevant precedent."""
    if not store:
        return "RR"
    algos = store[0]["per_algo_regret"].keys()
    means = {a: statistics.mean(regret_of(r, a) for r in store) for a in algos}
    return min(means, key=lambda a: means[a])


def predict_knn(query, store, k):
    if not store:
        return robust_default(store)
    return osmod.knn_predict(query["features"], store, k,
                             exclude_name=query["name"]) or robust_default(store)


def _nn_distance(query, store):
    nbrs = osmod.retrieve(query["features"], store, 1, exclude_name=query["name"])
    return nbrs[0]["distance"] if nbrs else None


def predict_knn_drift(query, store, k, recent_dists, z=2.0, warmup=4):
    """knn, but if the query is NOVEL (nearest-neighbour distance far above the
    recent baseline) distrust the stale store and use the robust default."""
    if not store:
        return robust_default(store), None
    d = _nn_distance(query, store)
    drift = False
    if d is not None and len(recent_dists) >= warmup:
        mu = statistics.mean(recent_dists)
        sd = statistics.pstdev(recent_dists) or 1e-9
        drift = d > mu + z * sd
    if drift:
        return robust_default(store), d  # novelty: fall back, don't trust nearest
    pred = osmod.knn_predict(query["features"], store, k,
                             exclude_name=query["name"]) or robust_default(store)
    return pred, d


# ── sequences ─────────────────────────────────────────────────────────────────
def seq_stable_blocks(records, fams):
    seq = []
    for f in fams:
        seq += [r for r in records if r["family"] == f]
    return seq


def seq_round_robin(records, fams):
    by_fam = {f: [r for r in records if r["family"] == f] for f in fams}
    seq, i = [], 0
    while any(by_fam[f][i:] for f in fams if i < len(by_fam[f])):
        for f in fams:
            if i < len(by_fam[f]):
                seq.append(by_fam[f][i])
        i += 1
    return seq


# ── replay one arm over one sequence ──────────────────────────────────────────
def replay(seq, predictor):
    """Online: at step t the store holds instances 0..t-1; predict, score the
    realised regret, then add the instance to the store."""
    store, series = [], []
    recent_dists = []  # for drift arm only
    for rec in seq:
        if predictor.__name__ == "_drift":
            algo, d = predictor(rec, store, recent_dists)
            if d is not None:
                recent_dists.append(d)
                recent_dists[:] = recent_dists[-8:]  # rolling window
        else:
            algo = predictor(rec, store)
        series.append({"name": rec["name"], "family": rec["family"],
                       "pred": algo, "true_best": rec["measured_best"],
                       "regret": round(regret_of(rec, algo), 3)})
        store.append(rec)
    return series


def precedent_bins(seq, series):
    """Bin each step's regret by how many SAME-FAMILY instances were already in
    the store when it was predicted (the store at step t = seq[0..t-1]). This is
    the order-independent test of the intuition: regret vs prior exposure to the
    pattern."""
    bins: dict[int, list[float]] = {}
    for t, (rec, s) in enumerate(zip(seq, series)):
        prior_same = sum(1 for r in seq[:t] if r["family"] == rec["family"])
        bins.setdefault(prior_same, []).append(s["regret"])
    return {c: {"n": len(v), "mean_regret": round(statistics.mean(v), 3)}
            for c, v in sorted(bins.items())}


def shuffle_labels(records, seed=1):
    """Randomly permute measured_best across instances (features +
    per_algo_regret stay REAL). Destroys the feature->winner signal knn
    retrieves on — the negative control. A true Fisher-Yates shuffle (a small
    rotation is NOT enough here: records are family-blocked and within-family
    labels are near-constant, so rotating leaves the signal intact)."""
    import random as _r
    rng = _r.Random(seed)
    labels = [r["measured_best"] for r in records]
    rng.shuffle(labels)
    return [dict(r, measured_best=labels[i]) for i, r in enumerate(records)]


def _sparkline(vals):
    blocks = "▁▂▃▄▅▆▇█"
    lo, hi = 0.0, max(0.001, max(vals))
    out = ""
    for v in vals:
        idx = int((v - lo) / (hi - lo) * (len(blocks) - 1))
        out += blocks[max(0, min(len(blocks) - 1, idx))]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--drift-z", type=float, default=2.0)
    args = ap.parse_args()

    bank = load_bank()
    records = bank["records"]
    fams = bank["families"]
    print(f"[replay] bank: {len(records)} instances, families={fams}\n")

    # predictors (closures over k)
    def knn(rec, store): return predict_knn(rec, store, args.k)
    def fixed_rr(rec, store): return "RR"
    def fixed_mlfq(rec, store): return "MLFQ"
    def _drift(rec, store, recent):
        return predict_knn_drift(rec, store, args.k, recent, z=args.drift_z)

    arms = {"fixed_rr": fixed_rr, "fixed_mlfq": fixed_mlfq,
            "knn": knn, "knn_drift": _drift}
    sequences = {"stable_blocks": seq_stable_blocks(records, fams),
                 "round_robin": seq_round_robin(records, fams)}

    results = {"k": args.k, "drift_z": args.drift_z,
               "families": fams, "n_instances": len(records),
               "sequences": {}}

    report = ["# Adaptive-learning replay — regret over a workload sequence\n",
              f"- bank: **{len(records)} instances**, families: {', '.join(fams)}",
              f"- k={args.k}, drift z={args.drift_z}, "
              f"regret = normalised gap from the measured-best on each instance's "
              f"target metric (0 = best).\n"]

    for sname, seq in sequences.items():
        results["sequences"][sname] = {"order": [r["name"] for r in seq], "arms": {}}
        report.append(f"\n## sequence: `{sname}`  (n={len(seq)})")
        report.append("families in order: " +
                       " ".join(r["family"][:3] for r in seq))
        report.append("")
        report.append("| arm | mean regret | series (low→high) |")
        report.append("|---|---|---|")
        knn_series = None
        for aname, pred in arms.items():
            series = replay(seq, pred)
            if aname == "knn":
                knn_series = series
            regs = [s["regret"] for s in series]
            mean_r = round(statistics.mean(regs), 3)
            results["sequences"][sname]["arms"][aname] = {
                "mean_regret": mean_r, "series": series}
            report.append(f"| {aname} | {mean_r} | `{_sparkline(regs)}` |")
            print(f"[{sname:13}] {aname:10} mean_regret={mean_r}  "
                  f"{_sparkline(regs)}")

        # ── intuition test: regret vs #same-family precedents (this sequence) ──
        pc = precedent_bins(seq, knn_series)
        results["sequences"][sname]["precedent_curve"] = pc
        report.append("")
        report.append("**knn regret vs # same-family precedents already seen** "
                       "(the intuition test):")
        report.append("")
        report.append("| same-family precedents | n | mean regret |")
        report.append("|---|---|---|")
        for c, v in pc.items():
            report.append(f"| {c} | {v['n']} | {v['mean_regret']} |")
        print(f"  precedent_curve: " +
              "  ".join(f"{c}:{v['mean_regret']}" for c, v in pc.items()))
        print()

    # ── negative control: shuffle stored labels, signal must collapse ─────────
    seq = seq_stable_blocks(records, fams)
    true_knn = round(statistics.mean(
        s["regret"] for s in replay(seq, knn)), 3)
    fixed_bar = min(results["sequences"]["stable_blocks"]["arms"][a]["mean_regret"]
                    for a in ("fixed_rr", "fixed_mlfq"))
    shuf_regrets = []
    for sd in range(1, 31):  # average over many random permutations
        shuffled = shuffle_labels(records, seed=sd)
        sseq = seq_stable_blocks(shuffled, fams)
        shuf_regrets.append(statistics.mean(s["regret"] for s in replay(sseq, knn)))
    shuf_knn = round(statistics.mean(shuf_regrets), 3)
    results["negative_control"] = {
        "true_label_knn": true_knn, "shuffled_label_knn": shuf_knn,
        "best_fixed_bar": fixed_bar,
        "verdict": ("signal real (shuffle collapses toward fixed bar)"
                    if shuf_knn >= fixed_bar - 0.02 else
                    "WARN: edge survives shuffling — likely artifact")}
    report.append("\n## negative control — label shuffle (signal vs artifact)\n")
    report.append("| condition | knn mean regret |")
    report.append("|---|---|")
    report.append(f"| true labels | {true_knn} |")
    report.append(f"| shuffled labels | {shuf_knn} |")
    report.append(f"| best fixed bar | {fixed_bar} |")
    report.append(f"\n**verdict:** {results['negative_control']['verdict']}")
    print(f"[neg-control] true_knn={true_knn}  shuffled_knn={shuf_knn}  "
          f"fixed_bar={fixed_bar}\n              -> "
          f"{results['negative_control']['verdict']}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(results, indent=2) + "\n")
    REPORT.write_text("\n".join(report) + "\n")
    print(f"[replay] wrote {RESULTS}\n[replay] wrote {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
