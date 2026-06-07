#!/usr/bin/env python3
"""adaptive_sched_eval.py — does OBSERVE-then-ADAPT (ODA) beat the best STATIC
Scheduling Algorithm on non-stationary workloads?

The premise (see the ODA design): on a workload whose optimal algorithm CHANGES
over time, no single static algorithm can be best throughout, so a scheduler that
starts on a safe default, observes the run, and switches ONCE should beat even the
best static choice. This script measures whether that headroom actually exists, in
the deterministic reference simulator (controlled A/B; simulator fidelity to xv6 is
irrelevant because every arm uses the identical model).

Arms measured per workload (lower metric = better; default avg_turnaround_time):
  B0  static default        : RR for the whole run (the safe baseline).
  B1  static oracle         : the best of all 6 static algorithms (the bar to beat).
  B2* oracle adaptive        : start RR, switch ONCE at the best (tick, to_algo)
                              found by exhaustive sweep — the ceiling of adaptation.
  B3  observed-rule adaptive : start RR, at a checkpoint DECIDE the switch from
                              ONLY the observed-so-far history (honest online rule).

Headroom = B1 - B2*. If positive, adaptation can beat the best static → the LLM
(which would replace the B3 rule with a learned decision) has something real to win.
Honesty: the decision in B3/LLM uses only OBSERVED past state at the checkpoint
(cur_burst_run, predicted_burst, completion) — never the hidden remaining burst.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from scheduler_simulator import Simulator, load_processes  # noqa: E402

WL_DIR = Path(__file__).resolve().parent / "adaptive_workloads"
OUT_DIR = PROJECT_ROOT / "outputs" / "adaptive"
ALGOS = ("RR", "FCFS", "PRIORITY", "MLFQ", "SJF", "SRTF")
DEFAULTS = {
    "RR":       {"quantum": 2},
    "FCFS":     {},
    "PRIORITY": {},
    "MLFQ":     {"queues": 3, "quantum": [2, 4, 8], "aging_threshold": 30},
    "SJF":      {},
    "SRTF":     {},
}


def _metric(m: dict, key: str):
    return m.get(key)


def run_static(procs, algo: str, switch_cost: int = 0) -> dict:
    return Simulator(copy.deepcopy(procs), algo, dict(DEFAULTS[algo]),
                     switch_cost=switch_cost).run()


def run_adaptive(procs, start: str, tc: int, to: str, switch_cost: int = 0) -> dict:
    plan = {"at": tc, "to": to, "params": dict(DEFAULTS[to])}
    return Simulator(copy.deepcopy(procs), start, dict(DEFAULTS[start]),
                     switch_plan=plan, switch_cost=switch_cost).run()


def observe(procs, start: str, tc: int, switch_cost: int = 0) -> dict:
    """Run the default to the checkpoint and snapshot ONLY observable state.
    Never reads p.remaining (hidden ground truth)."""
    sim = Simulator(copy.deepcopy(procs), start, dict(DEFAULTS[start]),
                    switch_cost=switch_cost)
    sim.run(max_ticks=tc)
    obs = []
    for p in sim.procs:
        obs.append({
            "pid": p.pid,
            "state": p.state,                  # FUTURE/RUNNABLE/RUNNING/DONE
            "cur_burst_run": p.cur_burst_run,  # observed ticks in current burst
            "predicted_burst": p.predicted_burst,
            "wait_ticks": p.wait_ticks,
            "done": p.state == "DONE",
        })
    active = [o for o in obs if not o["done"] and o["state"] != "FUTURE"]
    n_long = sum(1 for o in active if o["cur_burst_run"] >= 6)
    n_short_waiting = sum(1 for o in obs
                          if o["state"] == "RUNNABLE" and o["cur_burst_run"] == 0)
    return {"checkpoint_tick": tc, "default_algorithm": start,
            "observed_processes": obs,
            "signals": {"n_long_in_flight": n_long,
                        "n_short_waiting": n_short_waiting,
                        "n_active": len(active)}}


def decide_rule(observed: dict) -> str:
    """Deterministic, observation-only switch rule (the honest B3 baseline the
    LLM must beat). Long jobs in flight -> sequential FCFS; a pile of short
    waiters -> shortest-first SRTF; otherwise keep the responsive default."""
    s = observed["signals"]
    if s["n_long_in_flight"] >= 2:
        return "FCFS"
    if s["n_short_waiting"] >= 3:
        return "SRTF"
    return observed["default_algorithm"]


def tc_candidates(procs) -> list[int]:
    arrivals = sorted({p.arrival_time for p in procs})
    grid = list(range(2, max(arrivals) + 8, 2))
    return sorted(set(arrivals) | set(grid))


def evaluate(name: str, path: Path, metric: str, start: str, switch_cost: int = 0) -> dict:
    procs = load_processes(path)

    statics = {a: run_static(procs, a, switch_cost) for a in ALGOS}
    b0 = _metric(statics[start], metric)
    best_static_algo = min(ALGOS, key=lambda a: _metric(statics[a], metric))
    b1 = _metric(statics[best_static_algo], metric)

    # B2*: oracle adaptive over (tc, to)
    best = {"metric": float("inf"), "tc": None, "to": None}
    for tc in tc_candidates(procs):
        for to in ALGOS:
            if to == start:
                continue
            v = _metric(run_adaptive(procs, start, tc, to, switch_cost), metric)
            if v is not None and v < best["metric"]:
                best = {"metric": v, "tc": tc, "to": to}
    b2 = best["metric"]

    # B3: observed-rule adaptive. Pick the checkpoint as the first tick a long
    # job becomes observable, else the median arrival; decide the switch there.
    tcs = tc_candidates(procs)
    chosen_tc, chosen_to, b3 = tcs[len(tcs) // 2], start, None
    for tc in tcs:
        obs = observe(procs, start, tc, switch_cost)
        if obs["signals"]["n_long_in_flight"] >= 2 or obs["signals"]["n_short_waiting"] >= 3:
            chosen_tc = tc
            chosen_to = decide_rule(obs)
            break
    if chosen_to == start:
        b3 = b0
    else:
        b3 = _metric(run_adaptive(procs, start, chosen_tc, chosen_to, switch_cost), metric)

    headroom = round(b1 - b2, 2)
    b2_beats_b1 = b2 < b1 - 1e-9
    return {
        "workload": name, "metric": metric, "default_start": start,
        "B0_static_default": {"algo": start, "value": b0},
        "B1_static_oracle": {"algo": best_static_algo, "value": b1},
        "B2_oracle_adaptive": {"value": round(b2, 2), "switch_at": best["tc"],
                               "switch_to": best["to"]},
        "B3_observed_rule": {"value": round(b3, 2) if b3 is not None else None,
                             "switch_at": chosen_tc, "switch_to": chosen_to},
        "headroom_B1_minus_B2": headroom,
        "adaptive_beats_best_static": b2_beats_b1,
        "static_table": {a: round(_metric(statics[a], metric), 2) for a in ALGOS},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("workloads", nargs="*", help="workload names under adaptive_workloads/")
    ap.add_argument("--metric", default="avg_turnaround_time")
    ap.add_argument("--start", default="RR", help="safe default start algorithm")
    ap.add_argument("--switch-cost", type=int, default=0,
                    help="context-switch cost in ticks (0 = idealised cost-free sim)")
    ap.add_argument("--out", default=str(OUT_DIR / "adaptive_sched_eval.json"))
    args = ap.parse_args()

    names = args.workloads or [p.stem for p in sorted(WL_DIR.glob("*.json"))]
    rows = []
    for name in names:
        path = WL_DIR / f"{name}.json"
        if not path.is_file():
            print(f"[skip] {name}: not found")
            continue
        r = evaluate(name, path, args.metric, args.start.upper(), args.switch_cost)
        r["switch_cost"] = args.switch_cost
        rows.append(r)
        print(f"\n=== {name}  (metric={args.metric}, lower=better) ===")
        print(f"  static table: {r['static_table']}")
        st = r['default_start']
        print(f"  B0 static default ({st:5}) = {r['B0_static_default']['value']}")
        print(f"  B1 static oracle ({r['B1_static_oracle']['algo']:5}) = {r['B1_static_oracle']['value']}")
        print(f"  B2* oracle adaptive       = {r['B2_oracle_adaptive']['value']}  "
              f"({st} -> {r['B2_oracle_adaptive']['switch_to']} @ tick {r['B2_oracle_adaptive']['switch_at']})")
        print(f"  B3 observed-rule adaptive = {r['B3_observed_rule']['value']}  "
              f"({st} -> {r['B3_observed_rule']['switch_to']} @ tick {r['B3_observed_rule']['switch_at']})")
        verdict = "YES — adaptation beats best static" if r["adaptive_beats_best_static"] \
            else "no — best static already optimal"
        print(f"  headroom (B1-B2*) = {r['headroom_B1_minus_B2']}  -> {verdict}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"rows": rows}, indent=2) + "\n")
    print(f"\n[adaptive] wrote {args.out}")
    wins = sum(1 for r in rows if r["adaptive_beats_best_static"])
    print(f"[adaptive] adaptation beat best static on {wins}/{len(rows)} workloads")
    return 0


if __name__ == "__main__":
    sys.exit(main())
