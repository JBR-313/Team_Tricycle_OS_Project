"""
Scheduler Simulator — host-side fallback for xv6 scheduling.

Reads a workload JSON and a guard_decision JSON, simulates the chosen
scheduling algorithm, and emits:
  - trace JSONL  (outputs/trace_<algo>.jsonl)
  - metrics JSON (outputs/metrics.json)

Run:
    python3 tools/scheduler_simulator.py \\
        --workload workloads/interactive_heavy.json \\
        --guard    outputs/guard_decision.json \\
        --out-dir  outputs/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent

# Backward-compatible schema readers (tolerate algorithm / scheduling_algorithm)
sys.path.insert(0, str(Path(__file__).parent))
from schema_compat import get_guard_algorithm


# ── Process model ──────────────────────────────────────────────────────────
@dataclass
class Process:
    pid:          int
    arrival_time: int
    bursts:       list[int]      # CPU burst list
    priority:     int = 5        # lower = higher priority

    # runtime state
    burst_idx:   int = 0
    remaining:   int = 0         # remaining in current burst
    state:       str = "FUTURE"  # FUTURE | RUNNABLE | RUNNING | SLEEPING | DONE
    ctime:       int = 0         # creation tick (for FCFS tie-break)
    queue_level: int = 0         # MLFQ queue
    wait_ticks:  int = 0         # ticks in RUNNABLE (for aging)

    # metrics
    first_run_time:  Optional[int] = None
    finish_time:     Optional[int] = None

    def total_cpu(self) -> int:
        return sum(self.bursts)

    def activate(self):
        self.remaining = self.bursts[self.burst_idx] if self.bursts else 0
        self.state = "RUNNABLE"


# ── Trace emitter ───────────────────────────────────────────────────────────
class Tracer:
    def __init__(self, algo: str):
        self.algo = algo
        self.events: list[dict] = []

    def emit(self, tick: int, event: str, pid: int = -1, **extra):
        e: dict = {"tick": tick, "algo": self.algo, "event": event, "pid": pid}
        e.update(extra)
        self.events.append(e)

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            for ev in self.events:
                f.write(json.dumps(ev) + "\n")


# ── Simulator core ──────────────────────────────────────────────────────────
class Simulator:
    def __init__(self, processes: list[Process], algo: str, params: dict):
        self.procs   = processes
        self.algo    = algo.upper()
        self.params  = params
        self.tracer  = Tracer(algo)
        self.tick    = 0
        self.current: Optional[Process] = None
        self.dispatch_tick = 0
        self.preemption_count = 0

        # RR / MLFQ quantum
        if self.algo == "RR":
            self.quantum = params.get("quantum", 2)
            if isinstance(self.quantum, list):
                self.quantum = self.quantum[0]
        elif self.algo == "MLFQ":
            self.quanta    = params.get("quantum", [2, 4, 8])
            self.n_queues  = params.get("queues", 3)
            self.aging_thr = params.get("aging_threshold", 30)
        self.time_in_slice = 0

    # ── arrival helpers ──────────────────────────────────────────────────────
    def _arrive(self):
        for p in self.procs:
            if p.state == "FUTURE" and p.arrival_time <= self.tick:
                p.ctime = self.tick
                p.activate()
                self.tracer.emit(self.tick, "ARRIVE", p.pid,
                                 state="RUNNABLE", queue=p.queue_level,
                                 priority=p.priority, burst_hint=None)

    def _runnable(self) -> list[Process]:
        return [p for p in self.procs if p.state == "RUNNABLE"]

    def _all_done(self) -> bool:
        return all(p.state == "DONE" for p in self.procs)

    # ── algorithm pick functions ─────────────────────────────────────────────
    def _pick_rr(self) -> Optional[Process]:
        r = self._runnable()
        return min(r, key=lambda p: p.ctime) if r else None

    def _pick_fcfs(self) -> Optional[Process]:
        r = self._runnable()
        return min(r, key=lambda p: (p.arrival_time, p.pid)) if r else None

    def _pick_priority(self) -> Optional[Process]:
        # aging: every 20 ticks of waiting, effective priority +1
        r = self._runnable()
        if not r:
            return None
        def eff(p: Process) -> tuple:
            effective = p.priority - p.wait_ticks // 20
            return (effective, p.arrival_time, p.pid)
        return min(r, key=eff)

    def _pick_mlfq(self) -> Optional[Process]:
        # aging promotion
        for p in self._runnable():
            if p.wait_ticks >= self.aging_thr and p.queue_level > 0:
                old_q = p.queue_level
                p.queue_level = max(0, p.queue_level - 1)
                self.tracer.emit(self.tick, "QUEUE_CHANGE", p.pid,
                                 state="RUNNABLE",
                                 from_queue=old_q, to_queue=p.queue_level,
                                 reason="aging_promotion")
                p.wait_ticks = 0
        r = self._runnable()
        if not r:
            return None
        return min(r, key=lambda p: (p.queue_level, p.arrival_time, p.pid))

    def _pick_sjf(self) -> Optional[Process]:
        r = self._runnable()
        if not r:
            return None
        return min(r, key=lambda p: (p.remaining, p.pid))

    def _pick_srtf(self) -> Optional[Process]:
        r = self._runnable()
        if not r:
            return None
        return min(r, key=lambda p: (p.remaining, p.pid))

    def _pick(self) -> Optional[Process]:
        dispatch = {
            "RR": self._pick_rr,
            "FCFS": self._pick_fcfs,
            "PRIORITY": self._pick_priority,
            "MLFQ": self._pick_mlfq,
            "SJF": self._pick_sjf,
            "SRTF": self._pick_srtf,
        }
        return dispatch.get(self.algo, self._pick_rr)()

    # ── dispatch / preempt helpers ───────────────────────────────────────────
    def _dispatch(self, p: Process):
        p.state = "RUNNING"
        self.current = p
        self.dispatch_tick = self.tick
        self.time_in_slice = 0
        if p.first_run_time is None:
            p.first_run_time = self.tick
        self.tracer.emit(self.tick, "DISPATCH", p.pid,
                         state="RUNNING", queue=p.queue_level)

    def _preempt(self, p: Process, reason: str):
        p.state = "RUNNABLE"
        p.ctime = self.tick      # re-queue at end of RR queue
        self.preemption_count += 1
        self.tracer.emit(self.tick, "PREEMPT", p.pid,
                         state="RUNNABLE", queue=p.queue_level, reason=reason)
        if self.algo == "MLFQ" and reason == "quantum_expired":
            old_q = p.queue_level
            p.queue_level = min(self.n_queues - 1, p.queue_level + 1)
            if p.queue_level != old_q:
                self.tracer.emit(self.tick, "QUEUE_CHANGE", p.pid,
                                 state="RUNNABLE",
                                 from_queue=old_q, to_queue=p.queue_level,
                                 reason="demotion")
        self.current = None

    def _exit(self, p: Process):
        p.finish_time = self.tick
        p.state = "DONE"
        tat = p.finish_time - p.arrival_time
        wt  = tat - p.total_cpu()
        rt  = (p.first_run_time or self.tick) - p.arrival_time
        self.tracer.emit(self.tick, "EXIT", p.pid,
                         state="ZOMBIE", queue=p.queue_level,
                         turnaround=tat, waiting=max(0, wt), response=max(0, rt))
        self.current = None

    # ── quantum for current process ──────────────────────────────────────────
    def _quantum(self, p: Process) -> int:
        if self.algo == "RR":
            return self.quantum
        if self.algo == "MLFQ":
            return self.quanta[min(p.queue_level, len(self.quanta) - 1)]
        return 10_000  # effectively infinite for non-preemptive

    # ── main loop ────────────────────────────────────────────────────────────
    def run(self, max_ticks: int = 500) -> dict:
        # initialise remaining bursts
        for p in self.procs:
            p.remaining = p.bursts[0] if p.bursts else 0

        while not self._all_done() and self.tick < max_ticks:
            self._arrive()

            # increment wait ticks for all RUNNABLE
            for p in self._runnable():
                if p is not self.current:
                    p.wait_ticks += 1

            p = self.current
            if p is None or p.state != "RUNNING":
                # pick next
                nxt = self._pick()
                if nxt is None:
                    self.tick += 1
                    continue
                self._dispatch(nxt)
                p = self.current

            # execute one tick
            p.remaining      -= 1
            self.time_in_slice += 1
            p.wait_ticks      = 0

            # SRTF: check if a shorter job arrived
            if self.algo == "SRTF":
                shorter = [r for r in self._runnable() if r.remaining < p.remaining]
                if shorter:
                    self._preempt(p, "shorter_job")
                    self.tick += 1
                    continue

            # burst done?
            if p.remaining <= 0:
                p.burst_idx += 1
                if p.burst_idx >= len(p.bursts):
                    self._exit(p)
                else:
                    # more bursts (would do I/O — for simplicity, immediate re-queue)
                    p.remaining = p.bursts[p.burst_idx]
                    p.state = "RUNNABLE"
                    p.ctime = self.tick + 1
                    self.current = None
            elif self.algo in ("RR", "MLFQ") and self.time_in_slice >= self._quantum(p):
                self._preempt(p, "quantum_expired")
            # priority aging preemption
            elif self.algo == "PRIORITY":
                better = [r for r in self._runnable()
                          if (r.priority - r.wait_ticks // 20)
                          < (p.priority - p.wait_ticks // 20)]
                if better:
                    self._preempt(p, "higher_priority")

            self.tick += 1

        return self._compute_metrics()

    # ── metrics ──────────────────────────────────────────────────────────────
    def _compute_metrics(self) -> dict:
        done = [p for p in self.procs if p.state == "DONE"]
        if not done:
            return {}
        total_time = max(p.finish_time for p in done)
        per_proc = []
        for p in done:
            tat = p.finish_time - p.arrival_time
            wt  = tat - p.total_cpu()
            rt  = (p.first_run_time or 0) - p.arrival_time
            per_proc.append({
                "pid": p.pid,
                "arrival_time":   p.arrival_time,
                "first_run_time": p.first_run_time,
                "finish_time":    p.finish_time,
                "response_time":  max(0, rt),
                "turnaround_time": tat,
                "waiting_time":   max(0, wt),
            })

        avg_rt  = sum(x["response_time"]   for x in per_proc) / len(per_proc)
        avg_wt  = sum(x["waiting_time"]    for x in per_proc) / len(per_proc)
        avg_tat = sum(x["turnaround_time"] for x in per_proc) / len(per_proc)
        max_wt  = max(x["waiting_time"]    for x in per_proc)
        thruput = len(done) / total_time if total_time else 0.0

        return {
            "scheduling_algorithm": self.algo,
            "params": self.params,
            "process_count":        len(self.procs),
            "completed_count":      len(done),
            "total_execution_time": total_time,
            "avg_response_time":    round(avg_rt, 2),
            "avg_turnaround_time":  round(avg_tat, 2),
            "avg_waiting_time":     round(avg_wt, 2),
            "throughput":           round(thruput, 4),
            "max_waiting_time":     max_wt,
            "preemption_count":     self.preemption_count,
            "starvation_occurred":  max_wt > 60,
            "starvation_pids":      [x["pid"] for x in per_proc if x["waiting_time"] > 60],
            "per_process":          per_proc,
        }


# ── load helpers ────────────────────────────────────────────────────────────
def load_processes(wl_path: Path) -> list[Process]:
    with open(wl_path) as f:
        data = json.load(f)
    procs_raw = data if isinstance(data, list) else data.get("processes", [])
    procs = []
    for i, d in enumerate(procs_raw):
        bursts = d.get("cpu_bursts", d.get("bursts", [10]))
        procs.append(Process(
            pid=d.get("pid", i + 1),
            arrival_time=d.get("arrival_time", 0),
            bursts=bursts,
            priority=d.get("priority", 5),
        ))
    return procs


def run_all_algorithms(processes: list[Process], guard_params: dict,
                       rec_algo: str, out_dir: Path) -> dict:
    """Run all 6 algorithms and return a metrics dict with comparison."""
    all_results: dict[str, dict] = {}
    algos_params = {
        "RR":       {"quantum": 2},
        "FCFS":     {},
        "PRIORITY": {},
        "MLFQ":     {"queues": 3, "quantum": [2, 4, 8], "aging_threshold": 30},
        "SJF":      {},
        "SRTF":     {},
    }
    if rec_algo.upper() in algos_params:
        algos_params[rec_algo.upper()] = guard_params

    for algo, params in algos_params.items():
        import copy
        proc_copy = copy.deepcopy(processes)
        sim = Simulator(proc_copy, algo, params)
        m = sim.run()
        all_results[algo] = m
        trace_path = out_dir / f"trace_{algo.lower()}.jsonl"
        sim.tracer.save(trace_path)
        print(f"  [{algo}] avg_rt={m.get('avg_response_time')} "
              f"avg_wt={m.get('avg_waiting_time')} "
              f"preemptions={m.get('preemption_count')}")

    # find best avg_response_time
    best_rt = min(
        (v.get("avg_response_time", 999) for v in all_results.values()),
        default=999,
    )
    rec_rt = all_results.get(rec_algo.upper(), {}).get("avg_response_time", 999)
    delta = abs(rec_rt - best_rt) / (best_rt + 1e-9)
    if delta < 0.05:
        judgment = "SUCCESS"
        regret = round(delta, 3)
    elif delta < 0.25:
        judgment = "NEAR-SUCCESS"
        regret = round(delta, 3)
    else:
        judgment = "FAIL"
        regret = round(delta, 3)

    # build comparison dict (normalised algo names for dashboard)
    algo_display = {"RR": "RR", "FCFS": "FCFS", "PRIORITY": "Priority",
                    "MLFQ": "MLFQ", "SJF": "SJF", "SRTF": "SRTF"}
    comparison = {}
    judge_map = {}
    for algo_key, m in all_results.items():
        disp = algo_display.get(algo_key, algo_key)
        algo_rt = m.get("avg_response_time", 999)
        adelta = abs(algo_rt - best_rt) / (best_rt + 1e-9)
        aj = "SUCCESS" if adelta < 0.05 else ("NEAR-SUCCESS" if adelta < 0.25 else "FAIL")
        judge_map[algo_key] = aj
        comparison[disp] = {
            "avg_waiting_time":       m.get("avg_waiting_time"),
            "avg_response_time":      m.get("avg_response_time"),
            "avg_turnaround_time":    m.get("avg_turnaround_time"),
            "throughput":             m.get("throughput"),
            "max_waiting_time":       m.get("max_waiting_time"),
            "preemption_count":       m.get("preemption_count"),
            "starvation_occurred":    m.get("starvation_occurred", False),
            "burst_prediction_error": None,
            "judgment":               aj,
        }

    rec_m = all_results.get(rec_algo.upper(), {})
    metrics = {
        **rec_m,
        "comparison": comparison,
        "judgment": judgment,
        "regret_score": regret,
    }
    return metrics


# ── CLI ─────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="Host-side xv6 scheduler simulator")
    ap.add_argument("--workload", default=str(PROJECT_ROOT / "workloads" / "interactive_heavy.json"))
    ap.add_argument("--guard",    default=str(PROJECT_ROOT / "outputs" / "guard_decision.json"))
    ap.add_argument("--out-dir",  default=str(PROJECT_ROOT / "outputs"))
    args = ap.parse_args()

    wl_path   = Path(args.workload)
    guard_path = Path(args.guard)
    out_dir   = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not wl_path.exists():
        print(f"ERROR: workload not found: {wl_path}", file=sys.stderr)
        return 1

    # load guard decision
    rec_algo  = "MLFQ"
    guard_params: dict = {}
    if guard_path.exists():
        gd = json.load(open(guard_path))
        rec_algo = get_guard_algorithm(gd, rec_algo)
        guard_params = gd.get("params", {})
        print(f"Guard decision: {rec_algo} params={guard_params}")
    else:
        print(f"WARNING: guard_decision.json not found, using default {rec_algo}")

    print(f"Loading workload: {wl_path}")
    processes = load_processes(wl_path)
    print(f"  {len(processes)} processes")

    print("Simulating all algorithms...")
    metrics = run_all_algorithms(processes, guard_params, rec_algo, out_dir)

    metrics_path = out_dir / "metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nMetrics saved: {metrics_path}")
    print(f"Judgment: {metrics.get('judgment')}  regret={metrics.get('regret_score')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
