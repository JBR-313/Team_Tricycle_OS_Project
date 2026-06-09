#!/usr/bin/env python3
"""learning_curve_llm.py — does the LLM at the INTERFACE exploit the same
learned signal the no-LLM knn proved? Replays the measured bank through the
Solar advisor in two arms, online (store grows as instances are seen):

  llm_facts     (Arm A, no-learning) : advisor reasons from visible features
                                        only — no retrieved precedents.
  llm_retrieval (Arm B, learning)    : advisor + the k most similar PAST
                                        instances seen so far and their measured
                                        winner (outcome_store precedents).

Scored against the SAME bank regret table as learning_curve_replay.py, so the
LLM arms sit directly beside knn / fixed bars. Responses are cached under
outputs/learning/llm_cache/ (deterministic reruns, no repeat API spend).

No new xv6 runs and no real burst data: instance docs are reconstructed
deterministically from (family, seed) via learning_curve_bank.build_doc and
written to a throwaway dir so the advisor's load_workload path works unchanged
WITHOUT polluting workloads/.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tools"))

import learning_curve_bank as bankmod          # noqa: E402
import learning_curve_replay as rep            # noqa: E402
import retrieval_advisor as ra                 # noqa: E402

OUT_DIR = ROOT / "outputs" / "learning_curve"
DOCS_DIR = OUT_DIR / "llm_workloads"
K = 3


def _seed_of(name: str) -> int:
    return int(name.rsplit("_s", 1)[1])


def materialize_docs(records):
    """Reconstruct each instance doc deterministically and write it where the
    advisor's load_workload looks. Point ra.WORKLOADS_DIR at the throwaway dir."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    for r in records:
        doc = bankmod.build_doc(r["family"], _seed_of(r["name"]))
        (DOCS_DIR / f"{r['name']}.json").write_text(json.dumps(doc, indent=2))
    ra.WORKLOADS_DIR = DOCS_DIR  # advisor reads instance docs from here


def run_arm(seq, use_retrieval):
    """Online replay: at step t the store holds instances 0..t-1; ask the LLM,
    score realised regret, then add the instance to the store."""
    store, series = [], []
    for rec in seq:
        algo = ra.recommend_cached(rec, store, k=K, use_retrieval=use_retrieval,
                                   reps=1)
        series.append({"name": rec["name"], "family": rec["family"],
                       "pred": algo, "true_best": rec["measured_best"],
                       "regret": round(rep.regret_of(rec, algo), 3)})
        store.append(rec)
    return series


def main() -> int:
    bank = rep.load_bank()
    records = bank["records"]
    fams = bank["families"]
    materialize_docs(records)
    seq = rep.seq_stable_blocks(records, fams)
    print(f"[llm] {len(seq)} instances, families={fams}, k={K}\n")

    out = {}
    for arm, ur in (("llm_facts", False), ("llm_retrieval", True)):
        series = run_arm(seq, ur)
        regs = [s["regret"] for s in series]
        missing = sum(1 for s in series if s["pred"] is None)
        mean_r = round(statistics.mean(regs), 3)
        pc = rep.precedent_bins(seq, series)
        out[arm] = {"mean_regret": mean_r, "missing": missing,
                    "precedent_curve": pc, "series": series}
        print(f"[{arm:13}] mean_regret={mean_r}  (api-miss={missing})  "
              f"{rep._sparkline(regs)}")
        print("  precedent_curve: " +
              "  ".join(f"{c}:{v['mean_regret']}" for c, v in pc.items()))

    # fold into the main results.json beside knn / fixed bars
    res_path = OUT_DIR / "results.json"
    results = json.loads(res_path.read_text())
    results["llm_arms"] = out
    res_path.write_text(json.dumps(results, indent=2) + "\n")
    print(f"\n[llm] merged into {res_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
