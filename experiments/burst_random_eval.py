#!/usr/bin/env python3
"""burst_random_eval.py — leak-free, real-kernel, statistical test of whether the
LLM's cold-start burst prior improves SJF/SRTF over a blind EMA, across a
DISTRIBUTION of random workloads (docs/GOAL_burst_eval.md).

For each generated workload x strategy {ema_cold, heuristic, llm} x algo
{SRTF, SJF}: run on REAL xv6 via schedtest --procs (+ --hints priors), parse,
compute avg_waiting_time. Report, SEPARATELY for the SIGNAL and CONTROL regimes:
  - mean pairwise ordering accuracy per strategy (what SJF/SRTF consume), and
  - mean % improvement of llm (and heuristic) vs ema on avg_waiting, with a 95% CI.

The CONTROL regime (burst independent of features) is the built-in leak detector:
the LLM must NOT beat EMA there. xv6 is deterministic (-icount), so each workload
is run once per arm; statistical power comes from the number of workloads.

Honesty: actual bursts + hidden type are used to GENERATE/SCORE only; the prompt
sees visible features only (and llm_advisor strips description/id/label).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "experiments"))

import orchestrator as orch                       # noqa: E402
from metrics import compute_metrics               # noqa: E402
from workload_analyzer import analyze_workload    # noqa: E402
import burst_ablation as ba                        # noqa: E402
from workload_gen import generate_workload         # noqa: E402

OUT_DIR = ROOT / "outputs" / "random_eval"
RAW_DIR = OUT_DIR / "xv6"
CACHE = OUT_DIR / "llm_pred_cache.json"
METRIC = "avg_waiting_time"
STRATEGIES = ("ema_cold", "heuristic", "strong_heur", "llm")

# Type -> representative burst magnitude used by the graded heuristics.
_BURST_MAP = {"short": 3.0, "med": 11.0, "long": 25.0}


def predict_strong_heuristic(summary: dict) -> dict[int, float]:
    """A FAIR, multi-feature graded baseline — the bar the LLM must beat. It fuses
    BOTH visible signals (io_count AND priority, xv6: lower number = higher
    priority) into a graded burst estimate, instead of the binary single-feature
    rule in burst_ablation.predict_heuristic. If the LLM cannot beat THIS, the
    value is 'feature fusion', not 'LLM reasoning'."""
    out: dict[int, float] = {}
    for p in summary["visible_processes"]:
        io = p.get("io_count", 0) or 0
        pri = p.get("priority", 5) or 5
        t_io = "short" if io >= 3 else ("long" if io == 0 else "med")
        t_pri = "short" if pri <= 3 else ("long" if pri >= 7 else "med")
        out[int(p["pid"])] = (_BURST_MAP[t_io] + _BURST_MAP[t_pri]) / 2.0
    return out


def _spec(doc: dict) -> str:
    return ",".join(f"{p['arrival_time']}:{p['actual_bursts'][0]}:{p['priority']}"
                    for p in doc["processes"])


def _hints_csv(priors: dict[int, float], pids: list[int]) -> str:
    return ",".join(str(max(1, int(round(priors.get(pid, 10))))) for pid in pids)


def _prompt_key(summary: dict) -> str:
    from llm_advisor import build_user_prompt
    return hashlib.sha1(build_user_prompt(summary).encode()).hexdigest()[:16]


def _run_xv6(algo: str, spec: str, hints: str, tag: str) -> float | None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw = RAW_DIR / f"{tag}.log"
    pred = ["--procs", spec] + (["--hints", hints] if hints else [])
    if not orch.qemu_run_schedtest(algo.lower(), 42, "custom", raw, False, pred):
        return None
    trace = f"trace_{tag}.jsonl"
    orch.parse_xv6_log(raw, algo.upper(), 42, "custom", RAW_DIR, False, trace)
    tp = RAW_DIR / trace
    if not tp.is_file():
        return None
    m = compute_metrics(orch._load_jsonl(tp))
    return m.get(METRIC) if m else None


def _ci95(vals: list[float]) -> tuple[float, float, int]:
    n = len(vals)
    if n == 0:
        return (0.0, 0.0, 0)
    mean = sum(vals) / n
    if n < 2:
        return (mean, 0.0, n)
    var = sum((v - mean) ** 2 for v in vals) / (n - 1)
    return (mean, 1.96 * math.sqrt(var) / math.sqrt(n), n)


def _pct(ema: float, val: float) -> float | None:
    if ema in (None, 0) or val is None:
        return None
    return -100.0 * (val - ema) / ema   # positive = improvement (lower waiting)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-signal", type=int, default=8)
    ap.add_argument("--n-control", type=int, default=4)
    ap.add_argument("--procs", type=int, default=6)
    ap.add_argument("--base-seed", type=int, default=1000)
    ap.add_argument("--algos", default="SRTF,SJF")
    ap.add_argument("--signal", choices=["single", "multi"], default="multi",
                    help="single: io_count-only signal; multi: io_count AND "
                    "priority noisy signals (tests LLM vs a fair multi-feature rule)")
    ap.add_argument("--no-llm", action="store_true",
                    help="skip the LLM arm (validate plumbing with ema/heuristic only)")
    ap.add_argument("--out", default=str(OUT_DIR / "burst_random_eval.json"))
    args = ap.parse_args()
    algos = [a.strip().upper() for a in args.algos.split(",") if a.strip()]

    if not orch.ensure_xv6_built(False):
        print("xv6 build failed"); return 1

    # Build the workload set: (name, doc, regime).
    multi = (args.signal == "multi")
    work = []
    for k in range(args.n_signal):
        work.append((f"sig_{k:03d}",
                     generate_workload(args.base_seed + k, args.procs,
                                       control=False, multi=multi),
                     "signal"))
    for k in range(args.n_control):
        work.append((f"ctl_{k:03d}",
                     generate_workload(args.base_seed + 5000 + k, args.procs,
                                       control=True, multi=multi),
                     "control"))

    cache = json.loads(CACHE.read_text()) if CACHE.is_file() else {}
    client = None
    strategies = [s for s in STRATEGIES if not (s == "llm" and args.no_llm)]

    rows = []
    for name, doc, regime in work:
        summary = analyze_workload(doc, Path(f"{name}.json"))
        pids = [p["pid"] for p in doc["processes"]]
        actual = {p["pid"]: p["actual_bursts"][0] for p in doc["processes"]}
        spec = _spec(doc)

        priors = {
            "ema_cold": ba.predict_ema_cold(summary),
            "heuristic": ba.predict_heuristic(summary),
            "strong_heur": predict_strong_heuristic(summary),
        }
        if "llm" in strategies:
            key = f"{name}:{_prompt_key(summary)}"
            if key in cache:
                priors["llm"] = {int(k): float(v) for k, v in cache[key].items()}
            else:
                if client is None:
                    from solar_client import SolarClient
                    client = SolarClient()
                    print(f"[eval] eliciting LLM predictions via {client.model}")
                pred = ba.elicit_llm_predictions(summary, client)
                cache[key] = {str(k): v for k, v in pred.items()}
                CACHE.parent.mkdir(parents=True, exist_ok=True)
                CACHE.write_text(json.dumps(cache, indent=2) + "\n")
                priors["llm"] = pred

        order_acc = {s: ba._pairwise_order_accuracy(priors[s], actual) for s in strategies}
        waiting = {}
        for algo in algos:
            for s in strategies:
                tag = f"{name}_{algo.lower()}_{s}"
                waiting[(algo, s)] = _run_xv6(algo, spec, _hints_csv(priors[s], pids), tag)
        rows.append({"name": name, "regime": regime, "order_acc": order_acc,
                     "waiting": {f"{a}|{s}": waiting[(a, s)] for a in algos for s in strategies}})
        oa = "  ".join(f"{s}={order_acc[s]}" for s in strategies)
        print(f"  {name:8} [{regime:7}] order_acc: {oa}")

    # Aggregate per regime.
    report = {"regimes": {}, "config": vars(args)}
    for regime in ("signal", "control"):
        rr = [r for r in rows if r["regime"] == regime]
        if not rr:
            continue
        block = {"n_workloads": len(rr), "mean_order_acc": {}, "by_algo": {}}
        for s in strategies:
            accs = [r["order_acc"][s] for r in rr if r["order_acc"][s] is not None]
            block["mean_order_acc"][s] = round(sum(accs) / len(accs), 3) if accs else None
        for algo in algos:
            entry = {}
            ema_vals = [r["waiting"][f"{algo}|ema_cold"] for r in rr]
            for s in strategies:
                if s == "ema_cold":
                    continue
                pcts = []
                for r in rr:
                    e = r["waiting"][f"{algo}|ema_cold"]
                    v = r["waiting"][f"{algo}|{s}"]
                    pc = _pct(e, v)
                    if pc is not None:
                        pcts.append(pc)
                mean, ci, n = _ci95(pcts)
                entry[f"{s}_vs_ema_pct"] = {"mean": round(mean, 2),
                                            "ci95": round(ci, 2), "n": n}
            block["by_algo"][algo] = entry
        report["regimes"][regime] = block

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n")

    # Console summary.
    print("\n=== RESULTS (positive % = lower avg_waiting than blind EMA) ===")
    for regime, block in report["regimes"].items():
        print(f"\n[{regime}]  n={block['n_workloads']}  "
              f"mean ordering acc: {block['mean_order_acc']}")
        for algo, entry in block["by_algo"].items():
            for k, v in entry.items():
                print(f"    {algo:5} {k:18} = {v['mean']:+6.1f}%  ±{v['ci95']:.1f} (n={v['n']})")
    sig = report["regimes"].get("signal", {}).get("by_algo", {})
    ctl = report["regimes"].get("control", {}).get("by_algo", {})
    if "llm" in strategies and sig and ctl:
        print("\n[leak check] LLM must win on SIGNAL and ~tie on CONTROL.")
    print(f"\n[eval] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
