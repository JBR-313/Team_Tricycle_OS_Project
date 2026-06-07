#!/usr/bin/env python3
"""outcome_store.py — measured-outcome memory for retrieval-augmented advice.

This is the missing piece that closes the project's two core loops HONESTLY:

  Goal 1 ("LLM makes the best choice"): a fresh workload retrieves the measured
  best algorithm of the most SIMILAR past workloads and feeds those concrete
  precedents to the advisor, instead of reasoning blind from textbook priors.

  Goal 2 ("evaluate -> feedback -> improve"): every finished run already computes
  the true best via the exhaustive cross-algorithm comparison. Each such result
  is one (visible_features -> measured_best) example. Accumulating them here turns
  that comparison — previously thrown away — into the advisor's learning signal.
  As the store grows, recommendation accuracy should rise (a learning curve).

HONESTY CONTRACT (mirrors tools/llm_advisor.py):
  * Features are VISIBLE characterizations only (process_count, arrival gaps,
    cpu/interactive ratios, priority stats, burst COUNTS). Never per-process
    actual_bursts and never total_cpu_work (a burst aggregate). See
    `prompt_safe_features`.
  * The measured_best LABEL is the *evaluation answer* for that workload, so a
    workload must NEVER retrieve itself: callers use leave-one-out. The query's
    own expected_best_algorithm is also stripped from its prompt by the advisor.

Offline; no API key, no QEMU. Builds the store from workloads/*.json metadata
(expected_best_algorithm + expected_best_source) and the analyzer's features.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from workload_analyzer import analyze_workload, load_workload  # noqa: E402

WORKLOADS_DIR = PROJECT_ROOT / "workloads"

# Numeric features used for similarity. All are prompt-safe visible aggregates
# (no per-process burst durations, no total_cpu_work). burst_count_distribution
# is a count distribution (how many bursts), not their durations.
_NUMERIC_FEATURES = (
    "process_count",
    "avg_arrival_gap",
    "cpu_bound_ratio",
    "interactive_ratio",
    "avg_priority",
    "priority_variance",
    "burst_count_min",
    "burst_count_max",
    "burst_count_avg",
    "starvation_risk",  # 0/1
)


def prompt_safe_features(summary: dict) -> dict:
    """Flatten the analyzer summary into the prompt-safe numeric feature vector
    plus the categorical target_metric. Excludes total_cpu_work / answer keys."""
    bcd = summary.get("burst_count_distribution") or {}
    return {
        "process_count":     float(summary.get("process_count", 0)),
        "avg_arrival_gap":   float(summary.get("avg_arrival_gap", 0.0)),
        "cpu_bound_ratio":   float(summary.get("cpu_bound_ratio", 0.0)),
        "interactive_ratio": float(summary.get("interactive_ratio", 0.0)),
        "avg_priority":      float(summary.get("avg_priority", 0.0)),
        "priority_variance": float(summary.get("priority_variance", 0.0)),
        "burst_count_min":   float(bcd.get("min", 0)),
        "burst_count_max":   float(bcd.get("max", 0)),
        "burst_count_avg":   float(bcd.get("avg", 0.0)),
        "starvation_risk":   1.0 if summary.get("has_starvation_risk") else 0.0,
        "target_metric":     summary.get("target_metric") or "avg_response_time",
    }


def workload_record(path: Path) -> dict | None:
    """Build one outcome-store record from a workload JSON, or None if it carries
    no measured best label."""
    doc = load_workload(path)
    if isinstance(doc, list):
        return None
    best = doc.get("expected_best_algorithm")
    if not best:
        return None
    summary = analyze_workload(doc, path)
    feats = prompt_safe_features(summary)
    return {
        "name": path.stem,
        "features": feats,
        "measured_best": str(best).upper(),
        "source": doc.get("expected_best_source", "unknown"),
        "target_metric": feats["target_metric"],
    }


def build_store(source_filter: str | None = None,
                workloads_dir: Path = WORKLOADS_DIR) -> list[dict]:
    """Build the outcome store from all labeled workloads.

    source_filter: if given (e.g. 'xv6-measured'), keep only records whose
    expected_best_source matches — so an xv6 evaluation never mixes in
    simulator-measured labels (a different backend's best).
    """
    store = []
    for p in sorted(workloads_dir.glob("*.json")):
        rec = workload_record(p)
        if rec is None:
            continue
        if source_filter and rec["source"] != source_filter:
            continue
        store.append(rec)
    return store


# ── similarity / retrieval ───────────────────────────────────────────────────
def _norm_stats(store: list[dict]) -> dict[str, tuple[float, float]]:
    """Per-feature (mean, std) for z-normalization across the store."""
    stats = {}
    for f in _NUMERIC_FEATURES:
        vals = [r["features"][f] for r in store]
        mean = sum(vals) / len(vals) if vals else 0.0
        var = sum((v - mean) ** 2 for v in vals) / len(vals) if vals else 0.0
        std = math.sqrt(var) or 1.0
        stats[f] = (mean, std)
    return stats


def _best_threshold_acc(vals: list[float], labels: list[str]) -> float:
    """Univariate best-threshold binary-split accuracy for one feature. Used to
    weight features by how well they separate the winning algorithms. Computed
    ONLY on store records that exclude the query (leave-one-out) so it never
    peeks at the held-out answer."""
    classes = sorted(set(labels))
    if len(classes) < 2:
        return 0.0
    best = 0.0
    for t in sorted(set(vals)):
        for direction in (True, False):
            for hi, lo in ((classes[0], classes[1]), (classes[1], classes[0])):
                pred = [(hi if (v <= t if direction else v > t) else lo) for v in vals]
                acc = sum(p == l for p, l in zip(pred, labels)) / len(labels)
                best = max(best, acc)
    return best


def feature_weights(store: list[dict]) -> dict[str, float]:
    """Per-feature relevance weight = max(0, univariate_acc - 0.5), so a feature
    that cannot separate the classes contributes ~nothing and a strong separator
    dominates the distance. Equal-weight Euclidean drowns the few predictive
    features (avg_priority, process_count) under many irrelevant ones; this fixes
    that. Derived from `store` only — callers pass a query-excluded store for LOO."""
    labels = [r["measured_best"] for r in store]
    w = {}
    for f in _NUMERIC_FEATURES:
        vals = [r["features"][f] for r in store]
        w[f] = max(0.0, _best_threshold_acc(vals, labels) - 0.5)
    return w


def _distance(qf: dict, rf: dict, stats: dict, weights: dict[str, float] | None,
              target_weight: float = 1.0) -> float:
    """Weighted Euclidean distance over z-normalized numeric features, plus a
    categorical penalty when target_metric differs. `weights` (from
    feature_weights) scales each feature by its class-separating power; None =
    equal weight (the naive baseline)."""
    d2 = 0.0
    for f in _NUMERIC_FEATURES:
        mean, std = stats[f]
        zq = (qf[f] - mean) / std
        zr = (rf[f] - mean) / std
        w = 1.0 if weights is None else weights.get(f, 0.0)
        d2 += w * (zq - zr) ** 2
    if qf.get("target_metric") != rf.get("target_metric"):
        d2 += target_weight ** 2
    return math.sqrt(d2)


def retrieve(query_features: dict, store: list[dict], k: int,
             exclude_name: str | None = None, weighted: bool = True) -> list[dict]:
    """Return the k nearest store records to the query (leave-one-out via
    exclude_name). `weighted` enables the relevance-weighted distance (default);
    weights are computed on the query-EXCLUDED store, so no answer leakage. Each
    result carries an added 'distance' field."""
    pool = [r for r in store
            if exclude_name is None or r["name"] != exclude_name]
    if not pool:
        return []
    stats = _norm_stats(pool)
    weights = feature_weights(pool) if weighted else None
    cands = []
    for r in pool:
        d = _distance(query_features, r["features"], stats, weights)
        cands.append({**r, "distance": round(d, 4)})
    cands.sort(key=lambda x: x["distance"])
    return cands[:k]


def knn_predict(query_features: dict, store: list[dict], k: int,
                exclude_name: str | None = None) -> str | None:
    """No-LLM reference: majority measured_best among the k nearest (distance-
    weighted vote, nearest breaks ties)."""
    nbrs = retrieve(query_features, store, k, exclude_name)
    if not nbrs:
        return None
    votes: dict[str, float] = {}
    for n in nbrs:
        w = 1.0 / (1.0 + n["distance"])
        votes[n["measured_best"]] = votes.get(n["measured_best"], 0.0) + w
    return max(votes.items(), key=lambda kv: (kv[1],))[0]


def format_examples_for_prompt(neighbors: list[dict]) -> str:
    """Render retrieved precedents as few-shot lines for the advise prompt.
    Shows ONLY visible features + the measured winning algorithm — concrete
    evidence the advisor can reason from."""
    lines = []
    for n in neighbors:
        f = n["features"]
        lines.append(
            f"- past workload: procs={int(f['process_count'])}, "
            f"avg_arrival_gap={f['avg_arrival_gap']:.1f}, "
            f"cpu_ratio={f['cpu_bound_ratio']:.2f}, "
            f"interactive_ratio={f['interactive_ratio']:.2f}, "
            f"avg_priority={f['avg_priority']:.1f}, "
            f"prio_var={f['priority_variance']:.1f}, "
            f"burst_counts[min/avg/max]={int(f['burst_count_min'])}/"
            f"{f['burst_count_avg']:.1f}/{int(f['burst_count_max'])}, "
            f"target={n['target_metric']} "
            f"-> MEASURED BEST ON xv6: {n['measured_best']}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "xv6-measured"
    store = build_store(source_filter=None if src == "all" else src)
    print(f"outcome store ({src}): {len(store)} records")
    from collections import Counter
    print("  best distribution:", dict(Counter(r["measured_best"] for r in store)))
    for r in store:
        print(f"  {r['name']:28} best={r['measured_best']:6} target={r['target_metric']}")
