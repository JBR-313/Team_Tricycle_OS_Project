#!/usr/bin/env python3
"""burst_xv6_confirm.py — confirm the burst-prediction scheduling win on the REAL
xv6 kernel under QEMU. (The newer, leak-closed study with a negative control is
experiments/burst_random_eval.py.)

For each profile, runs xv6 SRTF (and SJF) TWICE on the identical workload:
  EMA cold-start : --alpha/--initial/--min/--max, NO --hints  -> every process
                   starts at the same predicted burst, so SRTF cannot tell jobs
                   apart and degenerates toward arrival order.
  LLM prior      : same predictor params PLUS --hints = the LLM's per-process
                   burst predictions (cached, visible-feature-only). SRTF can now
                   run the predicted-shortest job first.

The ONLY difference between the two arms is the burst priors, so the metric delta
is the LLM's contribution, measured on the real kernel. Reuses the orchestrator's
QEMU run + parse + metrics so it is the same execution path as the demo.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

import orchestrator as orch  # noqa: E402
from metrics import compute_metrics  # noqa: E402

PRED_CACHE = PROJECT_ROOT / "outputs" / "ablation" / "llm_predictions.json"
RAW_DIR = PROJECT_ROOT / "outputs" / "ablation" / "xv6_raw"
TRACE_DIR = PROJECT_ROOT / "outputs" / "ablation" / "xv6_traces"
METRICS = ("avg_waiting_time", "avg_turnaround_time", "avg_response_time")
EMA = ["--alpha", "50", "--initial", "10", "--min", "1", "--max", "100"]


def _hints_for(profile: str) -> list[int] | None:
    # schedtest uses the SHORT profile name (e.g. prio_starve); the mirror JSON
    # and the prediction cache use the xv6_ prefix (e.g. xv6_prio_starve).
    stem = f"xv6_{profile}"
    cache = json.loads(PRED_CACHE.read_text())
    preds = cache.get(stem)
    if not preds:
        return None
    wl = json.loads((PROJECT_ROOT / "workloads" / f"{stem}.json").read_text())
    order = [p["pid"] for p in wl["processes"]]
    return [max(1, int(round(float(preds[str(pid)])))) for pid in order
            if str(pid) in preds]


def _run_arm(algo: str, profile: str, seed: int, tag: str,
             pred_args: list[str]) -> dict | None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    raw = RAW_DIR / f"{profile}_{algo}_{tag}_seed{seed}.log"
    trace_name = f"trace_{profile}_{algo.lower()}_{tag}.jsonl"
    if not orch.qemu_run_schedtest(algo.lower(), seed, profile, raw, False, pred_args):
        print(f"    [warn] {algo} {tag}: no RUN_END captured")
        return None
    orch.parse_xv6_log(raw, algo, seed, profile, TRACE_DIR, False, trace_name)
    tp = TRACE_DIR / trace_name
    return compute_metrics(orch._load_jsonl(tp)) if tp.is_file() else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("profiles", nargs="*",
                    help="SHORT schedtest profile names, e.g. prio_starve convoy_tail")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--algos", default="SRTF,SJF")
    ap.add_argument("--out", default=str(PROJECT_ROOT / "outputs" / "ablation"
                                         / "burst_xv6_confirm.json"))
    args = ap.parse_args()
    profiles = args.profiles or ["prio_starve", "convoy_tail", "bimodal"]
    algos = [a.strip().upper() for a in args.algos.split(",") if a.strip()]

    if not orch.ensure_xv6_built(False):
        print("xv6 build failed"); return 1

    rows = []
    for profile in profiles:
        hints = _hints_for(profile)
        if not hints:
            print(f"[skip] {profile}: no cached LLM hints"); continue
        llm_args = EMA + ["--hints", ",".join(str(h) for h in hints)]
        print(f"\n=== {profile}  hints={hints} ===")
        entry = {"profile": profile, "hints": hints, "by_algo": {}}
        for algo in algos:
            ema_m = _run_arm(algo, profile, args.seed, "ema", EMA)
            llm_m = _run_arm(algo, profile, args.seed, "llm", llm_args)
            if not ema_m or not llm_m:
                continue
            rec = {}
            for k in METRICS:
                e, l = ema_m.get(k), llm_m.get(k)
                pct = (-100.0 * (l - e) / e) if (e not in (None, 0) and l is not None) else None
                rec[k] = {"ema": e, "llm": l, "pct_improvement": round(pct, 1) if pct is not None else None}
            entry["by_algo"][algo] = rec
            w = rec["avg_waiting_time"]
            print(f"  {algo:5} avg_wait  ema={w['ema']}  llm={w['llm']}  "
                  f"({w['pct_improvement']:+.1f}% )" if w['pct_improvement'] is not None
                  else f"  {algo}: n/a")
        rows.append(entry)

    Path(args.out).write_text(json.dumps({"seed": args.seed, "rows": rows}, indent=2) + "\n")
    print(f"\n[confirm] wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
