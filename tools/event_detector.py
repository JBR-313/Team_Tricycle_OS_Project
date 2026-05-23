"""
Event Detector — watches trace JSONL for scheduling problems and emits
runtime_events.json.

Detected problems:
  - starvation:   a process waits more than STARVATION_THRESHOLD ticks without CPU
  - low_thruput:  throughput below THRUPUT_THRESHOLD
  - high_preempt: preemption rate above PREEMPT_THRESHOLD per tick
  - long_rt:      avg response time above RESPONSE_THRESHOLD

Run:
    python3 tools/event_detector.py \\
        --trace   outputs/trace_mlfq.jsonl \\
        --metrics outputs/metrics.json \\
        --out     outputs/runtime_events.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

STARVATION_THRESHOLD = 40   # ticks without CPU = starvation warning
THRUPUT_THRESHOLD    = 0.05  # processes/tick
PREEMPT_THRESHOLD    = 0.30  # preemptions/tick
RESPONSE_THRESHOLD   = 10   # avg response time warning


def detect(events: list[dict], metrics: dict) -> list[dict]:
    problems: list[dict] = []

    # ── 1. starvation: track time without CPU per process ──────────────────
    last_cpu: dict[int, int] = {}
    arrived:  dict[int, int] = {}
    for ev in events:
        pid  = ev.get("pid", -1)
        tick = ev.get("tick", 0)
        et   = ev.get("event", "")
        if pid < 0:
            continue
        if et == "ARRIVE":
            arrived[pid] = tick
            last_cpu[pid] = tick
        elif et == "DISPATCH":
            last_cpu[pid] = tick
        elif et in ("PREEMPT", "WAKEUP"):
            # check gap since last CPU
            gap = tick - last_cpu.get(pid, tick)
            if gap >= STARVATION_THRESHOLD:
                problems.append({
                    "tick":    tick,
                    "type":    "starvation",
                    "pid":     pid,
                    "detail":  f"P{pid} waited {gap} ticks without CPU",
                    "severity":"high",
                })

    # ── 2. metrics-based checks ─────────────────────────────────────────────
    total_time  = metrics.get("total_execution_time", 1)
    preemptions = metrics.get("preemption_count", 0)
    thruput     = metrics.get("throughput", 0)
    avg_rt      = metrics.get("avg_response_time", 0)

    if thruput < THRUPUT_THRESHOLD:
        problems.append({
            "tick":    total_time,
            "type":    "low_throughput",
            "pid":     -1,
            "detail":  f"throughput={thruput:.3f} below threshold {THRUPUT_THRESHOLD}",
            "severity":"medium",
        })

    if total_time > 0 and preemptions / total_time > PREEMPT_THRESHOLD:
        problems.append({
            "tick":    total_time,
            "type":    "high_preemption_rate",
            "pid":     -1,
            "detail":  f"{preemptions} preemptions in {total_time} ticks "
                       f"({preemptions/total_time:.2f}/tick)",
            "severity":"low",
        })

    if avg_rt > RESPONSE_THRESHOLD:
        problems.append({
            "tick":    0,
            "type":    "high_response_time",
            "pid":     -1,
            "detail":  f"avg response time {avg_rt} exceeds threshold {RESPONSE_THRESHOLD}",
            "severity":"medium",
        })

    return sorted(problems, key=lambda p: p["tick"])


def main() -> int:
    ap = argparse.ArgumentParser(description="Detect scheduling problems from trace + metrics")
    ap.add_argument("--trace",   required=True)
    ap.add_argument("--metrics", required=True)
    ap.add_argument("--out",     default=str(PROJECT_ROOT / "outputs" / "runtime_events.json"))
    args = ap.parse_args()

    trace_path   = Path(args.trace)
    metrics_path = Path(args.metrics)
    out_path     = Path(args.out)

    if not trace_path.exists():
        print(f"ERROR: trace not found: {trace_path}", file=sys.stderr)
        return 1
    if not metrics_path.exists():
        print(f"ERROR: metrics not found: {metrics_path}", file=sys.stderr)
        return 1

    events = []
    for line in open(trace_path):
        s = line.strip()
        if s:
            try:
                events.append(json.loads(s))
            except Exception:
                pass

    metrics = json.load(open(metrics_path))
    problems = detect(events, metrics)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "total_problems": len(problems),
        "events": problems,
    }
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    if problems:
        print(f"Detected {len(problems)} problem(s):")
        for p in problems:
            print(f"  [{p['severity'].upper()}] tick={p['tick']} {p['type']}: {p['detail']}")
    else:
        print("No scheduling problems detected.")
    print(f"Saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
