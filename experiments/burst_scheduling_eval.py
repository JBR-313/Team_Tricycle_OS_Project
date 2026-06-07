#!/usr/bin/env python3
"""burst_scheduling_eval.py — does the LLM's burst prediction improve ACTUAL
SJF/SRTF scheduling outcomes, not just prediction accuracy?

burst_ablation.py showed the LLM wins on burst *ordering* (0.90 vs 0.50). This
closes the loop the project never measured: feed each prediction strategy's
priors into SJF/SRTF and measure the real schedule (avg waiting / turnaround /
response). It is the one place the LLM can produce a measurable PERFORMANCE win,
because SJF/SRTF schedule by predicted burst — better cold-start ordering ->
shorter jobs first -> lower waiting time.

Controlled A/B inside one simulator (the simulator's fidelity to xv6 is
irrelevant: BOTH arms use the identical model, so the delta isolates prediction
quality alone). Strategies:
  ema_cold  : one constant for everyone (the blind cold start) -> SJF degenerates
              to arrival order. This is the honest "no LLM" baseline; for single-
              burst jobs the kernel EMA never refines, so the constant is faithful.
  heuristic : fixed hand rule over visible features.
  llm       : the LLM's per-process prediction (cached, or elicited + cached).

Honesty: predictions come ONLY from visible features (burst_ablation reuses the
advisor's label-stripped prompt). actual_bursts drive execution + scoring only,
never a prediction. Reports % improvement of llm vs ema_cold on each metric.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))           # core pipeline modules
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling experiments/

import burst_ablation as ba  # noqa: E402
from scheduler_simulator import Simulator, load_processes  # noqa: E402
from workload_analyzer import analyze_workload, load_workload  # noqa: E402

OUT_DIR = PROJECT_ROOT / "outputs" / "ablation"
PRED_CACHE = OUT_DIR / "llm_predictions.json"
METRICS = ("avg_waiting_time", "avg_turnaround_time", "avg_response_time")


def _load_cache() -> dict:
    if PRED_CACHE.is_file():
        return json.loads(PRED_CACHE.read_text(encoding="utf-8"))
    return {}


def _llm_predictions(wid: str, summary: dict, cache: dict, advise: bool) -> dict[int, float]:
    cached = cache.get(wid)
    if cached and not advise:
        return {int(k): float(v) for k, v in cached.items()}
    if not advise:
        return {}
    from solar_client import SolarClient
    client = SolarClient()
    preds = ba.elicit_llm_predictions(summary, client)
    cache[wid] = {str(k): v for k, v in preds.items()}
    PRED_CACHE.parent.mkdir(parents=True, exist_ok=True)
    PRED_CACHE.write_text(json.dumps(cache, indent=2) + "\n", encoding="utf-8")
    return preds


def _run_with_priors(path: Path, algo: str, priors: dict[int, float]) -> dict:
    """Run SJF/SRTF in the simulator seeding each process's cold-start predicted
    burst from `priors` (prediction_source='llm' consumes llm_predicted_bursts)."""
    procs = load_processes(path)
    for p in procs:
        v = priors.get(p.pid)
        p.llm_predicted_bursts = [max(1, int(round(v)))] if v is not None else None
    sim = Simulator(copy.deepcopy(procs), algo, {}, prediction_source="llm")
    return sim.run()


def evaluate(workload_names: list[str], advise: bool) -> dict:
    cache = _load_cache()
    rows = []
    for name in workload_names:
        path = ba.resolve_workload_path(name)
        if not path.is_file():
            print(f"[skip] {name}: not found")
            continue
        doc = load_workload(path)
        summary = analyze_workload(doc, path)
        wid = doc.get("id", path.stem)

        strat_preds = {
            "ema_cold":  ba.predict_ema_cold(summary),
            "heuristic": ba.predict_heuristic(summary),
            "llm":       _llm_predictions(wid, summary, cache, advise),
        }
        if not strat_preds["llm"]:
            print(f"[skip] {name}: no LLM predictions (run with --advise to elicit)")
            continue

        per_algo = {}
        for algo in ("SJF", "SRTF"):
            per_strat = {}
            for strat, preds in strat_preds.items():
                m = _run_with_priors(path, algo, preds)
                per_strat[strat] = {k: m.get(k) for k in METRICS}
            per_algo[algo] = per_strat
        rows.append({"name": name, "id": wid,
                     "n": len(doc["processes"]), "by_algo": per_algo,
                     "target_metric": summary.get("target_metric")})
        # console line: SJF waiting, llm vs ema
        sjf = per_algo["SJF"]
        e = sjf["ema_cold"]["avg_waiting_time"]; l = sjf["llm"]["avg_waiting_time"]
        print(f"  {name:26} SJF avg_wait  ema={e:6.2f}  llm={l:6.2f}  "
              f"{'IMPROVED' if l < e else 'same/worse' if l >= e else ''} "
              f"({_pct(e, l):+.1f}%)")
    return {"rows": rows, "summary": _aggregate(rows)}


def _pct(base, val):
    if base in (None, 0) or val is None:
        return 0.0
    return -100.0 * (val - base) / base  # positive = improvement (lower is better)


def _aggregate(rows: list[dict]) -> dict:
    """Mean % improvement of llm vs ema_cold per (algo, metric), and a win count."""
    agg = {}
    for algo in ("SJF", "SRTF"):
        for metric in METRICS:
            deltas, wins, ties = [], 0, 0
            for r in rows:
                s = r["by_algo"][algo]
                e = s["ema_cold"][metric]; l = s["llm"][metric]
                if e is None or l is None:
                    continue
                deltas.append(_pct(e, l))
                if l < e:
                    wins += 1
                elif l == e:
                    ties += 1
            if deltas:
                agg[f"{algo}.{metric}"] = {
                    "mean_pct_improvement": round(sum(deltas) / len(deltas), 2),
                    "llm_better": wins, "ties": ties,
                    "llm_worse": len(deltas) - wins - ties, "n": len(deltas),
                }
    return agg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("workloads", nargs="*", help="workload names (default: a "
                    "burst-variance set across sim + xv6 profiles)")
    ap.add_argument("--advise", action="store_true",
                    help="elicit fresh LLM predictions (API) and cache them")
    ap.add_argument("--out", default=str(OUT_DIR / "burst_scheduling_eval.json"))
    args = ap.parse_args()

    names = args.workloads or [
        # simulator workloads with burst variance (cached predictions exist)
        "convoy_effect", "bursty_long_tail", "staggered_short_arrival",
        "burst_prediction_demo", "short_jobs",
        # xv6 profiles with burst variance (need --advise the first time)
        "xv6_convoy_tail", "xv6_bimodal", "xv6_preempt_stream",
        "xv6_burst_storm", "xv6_prio_starve",
    ]
    result = evaluate(names, advise=args.advise)

    print("\n=== AGGREGATE: LLM prior vs EMA cold-start (positive = LLM improves) ===")
    for key, a in result["summary"].items():
        print(f"  {key:28} mean {a['mean_pct_improvement']:+6.1f}%  "
              f"(llm better {a['llm_better']}/{a['n']}, "
              f"worse {a['llm_worse']}, ties {a['ties']})")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"\n[eval] wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
