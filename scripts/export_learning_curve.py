#!/usr/bin/env python3
"""export_learning_curve.py — derive the dashboard's Learning tab payload from
the MEASURED adaptive-learning study, never from hand-copied numbers.

Reads  outputs/learning_curve/results.json   (produced by experiments/
        learning_curve_bank.py -> _replay.py -> _llm.py on the real xv6 bank)
Writes dashboard_live/public/live-data/learning_curve.json  (curated aggregates)

WHY A SEPARATE, STATIC FILE (honesty):
  The learning curve is a CROSS-RUN, longitudinal result (regret vs how many
  same-family precedents the store has seen). It is NOT produced by a single
  dashboard RUN — a RUN is one live xv6 execution. So this payload is a
  measured-study artifact, badged `source: "measured"`, and the Learning tab
  labels it as such. It is regenerated only when the study is re-run, exactly
  like burst_ablation.json.

Every number here is a leave-one-out measured aggregate on the real-kernel
bank: visible features only, a workload never retrieves its own answer, and no
future burst durations are stored or shown.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "outputs" / "learning_curve" / "results.json"
DST = ROOT / "dashboard_live" / "public" / "live-data" / "learning_curve.json"


def _curve(pc: dict) -> list[dict]:
    """precedent_curve {"0": {n, mean_regret}, ...} -> sorted list of points."""
    return [
        {"precedents": int(k), "mean_regret": v["mean_regret"], "n": v["n"]}
        for k, v in sorted(pc.items(), key=lambda kv: int(kv[0]))
    ]


def build(results: dict) -> dict:
    sb = results["sequences"]["stable_blocks"]
    arms = sb["arms"]
    llm = results["llm_arms"]
    nc = results["negative_control"]

    # Bars are ordered worst -> best so the learning win reads left-to-right.
    bars = [
        {"key": "fixed_rr",      "label": "Always RR",       "kind": "baseline",
         "mean_regret": arms["fixed_rr"]["mean_regret"]},
        {"key": "llm_facts",     "label": "LLM (no memory)", "kind": "no_learning",
         "mean_regret": llm["llm_facts"]["mean_regret"]},
        {"key": "fixed_mlfq",    "label": "Always MLFQ",     "kind": "baseline",
         "mean_regret": arms["fixed_mlfq"]["mean_regret"]},
        {"key": "llm_retrieval", "label": "LLM + memory",    "kind": "learning",
         "mean_regret": llm["llm_retrieval"]["mean_regret"]},
        {"key": "knn",           "label": "Retrieval kNN",   "kind": "learning",
         "mean_regret": arms["knn"]["mean_regret"]},
    ]

    return {
        "source": "measured",
        "provenance": "outputs/learning_curve/results.json "
                      "(experiments/learning_curve_bank|replay|llm.py, real xv6 bank)",
        "k": results["k"],
        "families": results["families"],
        "n_instances": results["n_instances"],
        "precedent_curve": {
            "knn":           _curve(sb["precedent_curve"]),
            "llm_retrieval": _curve(llm["llm_retrieval"]["precedent_curve"]),
        },
        "arms": bars,
        "negative_control": {
            "true_label_knn":     nc["true_label_knn"],
            "shuffled_label_knn": nc["shuffled_label_knn"],
            "best_fixed_bar":     nc["best_fixed_bar"],
            "verdict":            nc["verdict"],
        },
        "drift": {
            "knn":       arms["knn"]["mean_regret"],
            "knn_drift": arms["knn_drift"]["mean_regret"],
            "z":         results["drift_z"],
            "verdict":   "self-heals within one instance of the new pattern; "
                         "no explicit drift-correction mechanism added",
        },
    }


def main() -> int:
    if not SRC.is_file():
        print(f"[export_learning_curve] missing {SRC}; run the study first "
              f"(experiments/learning_curve_*.py)", file=sys.stderr)
        return 1
    payload = build(json.loads(SRC.read_text()))
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"[export_learning_curve] {SRC.name} -> {DST}")
    print(f"  bars: " + "  ".join(f"{b['key']}={b['mean_regret']}" for b in payload["arms"]))
    print(f"  knn curve: " +
          " ".join(f"{p['precedents']}:{p['mean_regret']}"
                   for p in payload["precedent_curve"]["knn"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
