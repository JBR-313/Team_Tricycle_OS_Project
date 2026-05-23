"""
Metrics Evaluator — computes scheduling metrics from trace JSONL.

Reads trace_<algo>.jsonl and outputs metrics.json.

Run:
    python3 tools/metrics.py \\
        --trace  outputs/trace_mlfq.jsonl \\
        --rec    outputs/recommendation.json \\
        --out    outputs/metrics.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def compute(events: list[dict]) -> dict:
    """Compute per-process and aggregate metrics from trace events."""
    arrivals:   dict[int, int]  = {}
    first_runs: dict[int, int]  = {}
    finishes:   dict[int, int]  = {}
    cpu_work:   dict[int, int]  = {}
    dispatch_at: dict[int, int] = {}
    preemptions = 0

    for ev in events:
        pid  = ev.get("pid", -1)
        tick = ev.get("tick", 0)
        et   = ev.get("event", "")

        if pid < 0:
            continue

        if et == "ARRIVE":
            arrivals[pid] = tick
            cpu_work[pid] = 0

        elif et == "DISPATCH":
            dispatch_at[pid] = tick
            if pid not in first_runs:
                first_runs[pid] = tick

        elif et in ("PREEMPT", "SLEEP"):
            if pid in dispatch_at:
                cpu_work[pid] = cpu_work.get(pid, 0) + (tick - dispatch_at.pop(pid))
            if et == "PREEMPT":
                preemptions += 1

        elif et == "EXIT":
            # prefer explicit fields from simulator
            tat = ev.get("turnaround")
            wt  = ev.get("waiting")
            rt  = ev.get("response")
            if tat is None:
                if pid in dispatch_at:
                    cpu_work[pid] = cpu_work.get(pid, 0) + (tick - dispatch_at.pop(pid))
                arr = arrivals.get(pid, 0)
                tat = tick - arr
                wt  = max(0, tat - cpu_work.get(pid, 0))
                rt  = max(0, first_runs.get(pid, tick) - arr)
            finishes[pid] = {
                "arrival_time":    arrivals.get(pid, 0),
                "first_run_time":  first_runs.get(pid, tick),
                "finish_time":     tick,
                "turnaround_time": tat,
                "waiting_time":    wt,
                "response_time":   rt,
            }

    if not finishes:
        return {}

    per_proc = [{"pid": pid, **v} for pid, v in finishes.items()]
    n = len(per_proc)
    total_time = max(v["finish_time"] for v in finishes.values())

    avg_rt  = sum(v["response_time"]   for v in finishes.values()) / n
    avg_wt  = sum(v["waiting_time"]    for v in finishes.values()) / n
    avg_tat = sum(v["turnaround_time"] for v in finishes.values()) / n
    max_wt  = max(v["waiting_time"]    for v in finishes.values())
    thruput = n / total_time if total_time else 0.0
    starv   = max_wt > 60
    starv_pids = [pid for pid, v in finishes.items() if v["waiting_time"] > 60]

    return {
        "process_count":        n,
        "completed_count":      n,
        "total_execution_time": total_time,
        "avg_response_time":    round(avg_rt, 2),
        "avg_turnaround_time":  round(avg_tat, 2),
        "avg_waiting_time":     round(avg_wt, 2),
        "throughput":           round(thruput, 4),
        "max_waiting_time":     max_wt,
        "preemption_count":     preemptions,
        "starvation_occurred":  starv,
        "starvation_pids":      starv_pids,
        "per_process":          per_proc,
    }


def evaluate_judgment(m: dict, rec_algo: str, all_metrics: dict[str, dict]) -> dict:
    """Add judgment and regret_score based on comparison to all algorithms."""
    target = "avg_response_time"
    rec_rt = m.get(target, 999)
    best_rt = min(
        (v.get(target, 999) for v in all_metrics.values()),
        default=999,
    )
    delta = abs(rec_rt - best_rt) / (best_rt + 1e-9)
    judgment  = "SUCCESS" if delta < 0.05 else ("NEAR-SUCCESS" if delta < 0.25 else "FAIL")
    m["judgment"]     = judgment
    m["regret_score"] = round(delta, 3)
    return m


def main() -> int:
    ap = argparse.ArgumentParser(description="Compute metrics from trace JSONL")
    ap.add_argument("--trace", required=True, help="Trace JSONL file")
    ap.add_argument("--rec",   default="",   help="recommendation.json (for algo name)")
    ap.add_argument("--out",   default=str(PROJECT_ROOT / "outputs" / "metrics.json"))
    args = ap.parse_args()

    trace_path = Path(args.trace)
    out_path   = Path(args.out)

    if not trace_path.exists():
        print(f"ERROR: trace not found: {trace_path}", file=sys.stderr)
        return 1

    events = []
    for line in open(trace_path):
        s = line.strip()
        if s:
            try:
                events.append(json.loads(s))
            except Exception:
                pass

    algo = events[0].get("algo", "UNKNOWN") if events else "UNKNOWN"
    m = compute(events)
    if not m:
        print("ERROR: no EXIT events found in trace", file=sys.stderr)
        return 1

    m["scheduling_algorithm"] = algo

    # load rec if available
    rec_algo = algo
    if args.rec:
        rec_p = Path(args.rec)
        if rec_p.exists():
            rec = json.load(open(rec_p))
            rec_algo = rec.get("recommended_scheduling_algorithm", algo)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(m, f, indent=2)
    print(f"Metrics saved: {out_path}")
    print(f"  avg_rt={m['avg_response_time']}  avg_wt={m['avg_waiting_time']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
