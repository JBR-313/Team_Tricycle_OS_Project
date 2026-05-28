"""Scheduler Simulator — DEV / FALLBACK only, NOT the final demo backend.

Role classification (see docs/codebase_slimming_plan.md §2.2):
  DEV / FALLBACK — used by `scripts/orchestrator.py --backend simulator` when
  QEMU/xv6 is unavailable, and by host-side smoke tests. It is a Python
  model of the algorithms, **not** proof of real xv6 execution. The dashboard
  surfaces this with a `SIMULATOR FALLBACK` badge.

The final demo execution path is `--backend xv6` (real QEMU + xv6 +
schedtest). Do not present simulator output as the final result.

Caveat: SJF/SRTF in this simulator currently use the *actual* remaining
burst (oracle), unlike the xv6 kernel which uses an exponential-averaging
predictor. See docs/sjf_srtf_prediction_audit.md.

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
from schema_compat import (
    get_guard_algorithm,
    get_recommended_algorithm,
    is_higher_better_metric,
    normalize_target_metric,
)


# ── Hidden-burst separation (matches xv6 kernel: docs/sjf_srtf_prediction_audit.md)
# `actual_bursts` are the ground-truth runtime values: used by execution
# (decrementing `remaining`) and by evaluation. SJF/SRTF MUST NOT read them.
# `predicted_burst` is the scheduler-visible value used by SJF/SRTF picks; it
# is seeded from the LLM hint (or the EMA initial) and refreshed by the EMA
# update at the end of each observed CPU burst.
@dataclass
class Predictor:
    """Exponential-averaging burst predictor (xv6-compatible defaults).

    tau_next = (alpha * observed + (100 - alpha) * tau_prev) / 100
    """
    alpha_percent: int = 50
    initial:       int = 10
    min:           int = 1
    max:           int = 100

    def update(self, observed: int, prev: int) -> int:
        if observed <= 0:
            return prev
        v = (self.alpha_percent * observed + (100 - self.alpha_percent) * prev) // 100
        if v < self.min: v = self.min
        if v > self.max: v = self.max
        return v


@dataclass
class Process:
    pid:          int
    arrival_time: int
    bursts:       list[int]      # ACTUAL (hidden) CPU burst list — execution truth
    priority:     int = 5        # lower = higher priority

    # runtime state
    burst_idx:   int = 0
    remaining:   int = 0         # remaining in current ACTUAL burst
    state:       str = "FUTURE"  # FUTURE | RUNNABLE | RUNNING | SLEEPING | DONE
    ctime:       int = 0         # creation tick (for FCFS tie-break)
    queue_level: int = 0         # MLFQ queue
    wait_ticks:  int = 0         # ticks in RUNNABLE (for aging)

    # SJF/SRTF predictor state — the only burst-related fields the scheduler may read.
    predicted_burst:       int = 10     # current EMA / LLM estimate of next burst
    cur_burst_run:         int = 0      # observed CPU consumed in current burst so far
    llm_predicted_bursts:  Optional[list[int]] = None  # per-burst LLM hints (optional)

    # metrics
    first_run_time:  Optional[int] = None
    finish_time:     Optional[int] = None

    def total_cpu(self) -> int:
        return sum(self.bursts)

    def activate(self):
        self.remaining = self.bursts[self.burst_idx] if self.bursts else 0
        self.cur_burst_run = 0
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
    def __init__(self, processes: list[Process], algo: str, params: dict,
                 prediction_source: str = "ema"):
        """
        prediction_source:
          - "ema"  (default): seed predicted_burst from predictor.initial, refine
                              via exponential averaging as bursts are observed.
          - "llm"            : seed predicted_burst from per-process LLM hints
                              (Process.llm_predicted_bursts[burst_idx]) when
                              available; fall back to EMA otherwise. Still
                              refines via EMA after each observed burst.
        """
        self.procs   = processes
        self.algo    = algo.upper()
        self.params  = params
        self.tracer  = Tracer(algo)
        self.tick    = 0
        self.current: Optional[Process] = None
        self.dispatch_tick = 0
        self.preemption_count = 0
        self.prediction_source = prediction_source

        # SJF/SRTF burst predictor (xv6-kernel-compatible defaults; params may
        # be overridden by the guard for predictive algorithms).
        self.predictor = Predictor(
            alpha_percent=int(params.get("alpha_percent", 50)),
            initial=int(params.get("initial", 10)),
            min=int(params.get("min", 1)),
            max=int(params.get("max", 100)),
        )

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

    # ── predictor helpers ────────────────────────────────────────────────────
    def _seed_predicted(self, p: Process):
        """Seed predicted_burst for the *current* burst index.
        LLM hints take precedence when prediction_source == 'llm' and the
        per-process hint list is long enough; otherwise use the predictor
        initial (or keep the prior EMA value if we already have one)."""
        if self.prediction_source == "llm" and p.llm_predicted_bursts \
                and p.burst_idx < len(p.llm_predicted_bursts):
            hint = int(p.llm_predicted_bursts[p.burst_idx])
            hint = max(self.predictor.min, min(self.predictor.max, hint))
            p.predicted_burst = hint
        elif p.predicted_burst <= 0:
            p.predicted_burst = self.predictor.initial

    def _update_prediction(self, p: Process):
        """End-of-burst EMA refresh; mirrors xv6 update_burst_prediction()."""
        new = self.predictor.update(p.cur_burst_run, p.predicted_burst)
        if new != p.predicted_burst:
            self.tracer.emit(self.tick, "PRED_UPDATE", p.pid,
                             observed=p.cur_burst_run,
                             predicted_prev=p.predicted_burst,
                             predicted_next=new,
                             source=self.prediction_source)
        p.predicted_burst = new
        p.cur_burst_run = 0

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
        """Predicted SJF — uses predicted_burst, NEVER p.remaining (ground truth)."""
        r = self._runnable()
        if not r:
            return None
        return min(r, key=lambda p: (p.predicted_burst, p.ctime, p.pid))

    def _pick_srtf(self) -> Optional[Process]:
        """Predicted SRTF — predicted_burst minus already-observed cur_burst_run,
        floored at predictor.min. Never reads p.remaining (ground truth)."""
        r = self._runnable()
        if not r:
            return None
        def pred_remaining(p: Process) -> int:
            v = p.predicted_burst - p.cur_burst_run
            return max(self.predictor.min, v)
        return min(r, key=lambda p: (pred_remaining(p), p.ctime, p.pid))

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
        # initialise execution-side (hidden) remaining bursts and
        # scheduler-visible predicted_burst for each process.
        for p in self.procs:
            p.remaining = p.bursts[0] if p.bursts else 0
            p.cur_burst_run = 0
            self._seed_predicted(p)

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

            # execute one tick (decrement ACTUAL remaining and increment OBSERVED run)
            p.remaining       -= 1
            p.cur_burst_run   += 1
            self.time_in_slice += 1
            p.wait_ticks       = 0

            # SRTF preemption check — uses PREDICTED remaining, never the hidden truth.
            if self.algo == "SRTF":
                def _pred_rem(q: Process) -> int:
                    return max(self.predictor.min, q.predicted_burst - q.cur_burst_run)
                my_pred_rem = _pred_rem(p)
                shorter = [r for r in self._runnable() if _pred_rem(r) < my_pred_rem]
                if shorter:
                    self._preempt(p, "shorter_job")
                    self.tick += 1
                    continue

            # burst done?
            if p.remaining <= 0:
                # Update EMA prediction at end of observed burst (xv6 parity).
                self._update_prediction(p)
                p.burst_idx += 1
                if p.burst_idx >= len(p.bursts):
                    self._exit(p)
                else:
                    # more bursts (would do I/O — for simplicity, immediate re-queue)
                    p.remaining = p.bursts[p.burst_idx]
                    p.state = "RUNNABLE"
                    p.ctime = self.tick + 1
                    self.current = None
                    self._seed_predicted(p)
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
    """Load processes from a workload file.

    v2 schema uses `actual_bursts` (the hidden execution truth). For backward
    compatibility, fall back to legacy `cpu_bursts` then `bursts`. Optional
    `llm_predicted_bursts` per process supplies LLM burst hints used only when
    Simulator(prediction_source='llm').
    """
    with open(wl_path) as f:
        data = json.load(f)
    procs_raw = data if isinstance(data, list) else data.get("processes", [])
    procs = []
    for i, d in enumerate(procs_raw):
        actual = d.get("actual_bursts") or d.get("cpu_bursts") or d.get("bursts") or [10]
        llm_hints = d.get("llm_predicted_bursts")
        procs.append(Process(
            pid=d.get("pid", i + 1),
            arrival_time=d.get("arrival_time", 0),
            bursts=list(actual),
            priority=d.get("priority", 5),
            llm_predicted_bursts=list(llm_hints) if llm_hints else None,
        ))
    return procs


def attach_llm_hints(processes: list[Process], predicted_bursts: list[dict]):
    """Attach LLM burst hints (from recommendation.predicted_bursts) to procs.

    `predicted_bursts` is a list like [{"pid": 1, "predicted_burst": 5.2}, ...]
    or [{"pid": 1, "predicted_bursts": [3, 2]}]. Each is folded into the
    matching Process's llm_predicted_bursts.
    """
    by_pid = {h.get("pid"): h for h in (predicted_bursts or [])}
    for p in processes:
        h = by_pid.get(p.pid)
        if not h:
            continue
        if "predicted_bursts" in h and isinstance(h["predicted_bursts"], list):
            p.llm_predicted_bursts = [int(round(float(x))) for x in h["predicted_bursts"]]
        elif "predicted_burst" in h:
            p.llm_predicted_bursts = [int(round(float(h["predicted_burst"])))]


def run_all_algorithms(processes: list[Process], guard_params: dict,
                       rec_algo: str, out_dir: Path,
                       target_metric: str = "avg_response_time",
                       prediction_source: str = "ema") -> dict:
    """Run all 6 algorithms and return a metrics dict with comparison.

    prediction_source: "ema" (EMA baseline; default) or "llm" (use any
    Process.llm_predicted_bursts hints attached via attach_llm_hints()).
    """
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
        # SJF/SRTF respect the prediction_source choice; other algorithms ignore it.
        psrc = prediction_source if algo in ("SJF", "SRTF") else "ema"
        sim = Simulator(proc_copy, algo, params, prediction_source=psrc)
        m = sim.run()
        m["prediction_source"] = psrc if algo in ("SJF", "SRTF") else None
        all_results[algo] = m
        trace_path = out_dir / f"trace_{algo.lower()}.jsonl"
        sim.tracer.save(trace_path)
        print(f"  [{algo}] avg_rt={m.get('avg_response_time')} "
              f"avg_wt={m.get('avg_waiting_time')} "
              f"preemptions={m.get('preemption_count')}"
              f"{f' pred={psrc}' if algo in ('SJF','SRTF') else ''}")

    # Metric-aware judgment (canonical thresholds; starvation forces FAIL).
    # regret(lower-better) = (val-best)/|best|; regret(higher-better) = (best-val)/|best|
    # Single source of truth: tools/metrics.py {SUCCESS_REGRET, NEAR_SUCCESS_REGRET}.
    from metrics import SUCCESS_REGRET, NEAR_SUCCESS_REGRET
    JUDGE_KEYS = {
        "avg_response_time", "avg_waiting_time", "avg_turnaround_time",
        "throughput", "max_waiting_time", "preemption_count",
    }
    metric_key = normalize_target_metric(target_metric)
    if metric_key not in JUDGE_KEYS:
        metric_key = "avg_response_time"
    higher = is_higher_better_metric(metric_key)
    vals = [v.get(metric_key) for v in all_results.values()
            if isinstance(v.get(metric_key), (int, float))]
    best_val = (max(vals) if higher else min(vals)) if vals else 0.0

    def _judge(m: dict):
        if m.get("starvation_occurred"):
            return "FAIL", 1.0
        val = m.get(metric_key)
        if not isinstance(val, (int, float)):
            return "UNKNOWN", 0.0
        denom = max(abs(best_val), 1e-9)
        d = round((best_val - val) / denom if higher else (val - best_val) / denom, 3)
        if d <= SUCCESS_REGRET:
            return "SUCCESS", d
        if d <= NEAR_SUCCESS_REGRET:
            return "NEAR-SUCCESS", d
        return "FAIL", d

    # build comparison dict (normalised display algo names for dashboard)
    algo_display = {"RR": "RR", "FCFS": "FCFS", "PRIORITY": "Priority",
                    "MLFQ": "MLFQ", "SJF": "SJF", "SRTF": "SRTF"}
    comparison = {}
    for algo_key, m in all_results.items():
        disp = algo_display.get(algo_key, algo_key)
        aj, _ = _judge(m)
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
    judgment, regret = _judge(rec_m)

    # v2 evaluation fields (mirror tools/metrics._explain_judgment / evaluate_run).
    best_algo = None
    best_val_v = None
    cands = [(a, m.get(metric_key)) for a, m in all_results.items()
             if isinstance(m.get(metric_key), (int, float))]
    if cands:
        chooser = max if higher else min
        best_algo, best_val_v = chooser(cands, key=lambda x: x[1])
    sel_val = rec_m.get(metric_key)
    sel_algo_disp = algo_display.get(rec_algo.upper(), rec_algo.upper())

    if rec_m.get("starvation_occurred"):
        explanation = (
            f"FAIL: {sel_algo_disp} caused starvation"
            + (f" on pid(s) {rec_m.get('starvation_pids')}" if rec_m.get('starvation_pids') else "")
            + " — starvation forces FAIL regardless of regret."
        )
    elif regret is None or sel_val is None or best_val_v is None or best_algo is None:
        explanation = f"UNKNOWN: insufficient comparison data for {sel_algo_disp} on {metric_key}."
    else:
        raw_pct = regret * 100
        if raw_pct >= 999.5:
            pct_str, tail = ">999%", " (regret huge because best≈0)"
        else:
            pct_str, tail = f"{round(raw_pct, 1)}%", ""
        bound = ("(<= 10%)" if judgment == "SUCCESS"
                 else "(10-25%)" if judgment == "NEAR-SUCCESS" else "(> 25%)")
        best_disp = algo_display.get(best_algo, best_algo)
        explanation = (
            f"{judgment}: {sel_algo_disp} on {metric_key} = {sel_val} vs "
            f"best ({best_disp}) = {best_val_v}; regret = {pct_str} {bound}.{tail}"
        )

    metrics = {
        **rec_m,
        "comparison": comparison,
        "judgment": judgment,
        "regret_score": regret,
        "target_metric": metric_key,
        "selected_metric_value": sel_val,
        "best_algorithm": algo_display.get(best_algo, best_algo) if best_algo else None,
        "best_metric_value": best_val_v,
        "explanation": explanation,
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
    target_metric = "avg_response_time"
    if guard_path.exists():
        gd = json.load(open(guard_path))
        rec_algo = get_guard_algorithm(gd, rec_algo)
        guard_params = gd.get("params", {})
        target_metric = normalize_target_metric(gd.get("target_metric"))
        print(f"Guard decision: {rec_algo} params={guard_params} target={target_metric}")
    else:
        print(f"WARNING: guard_decision.json not found, using default {rec_algo}")

    print(f"Loading workload: {wl_path}")
    processes = load_processes(wl_path)
    print(f"  {len(processes)} processes")

    print("Simulating all algorithms...")
    metrics = run_all_algorithms(processes, guard_params, rec_algo, out_dir, target_metric)

    metrics_path = out_dir / "metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nMetrics saved: {metrics_path}")
    print(f"Judgment: {metrics.get('judgment')}  regret={metrics.get('regret_score')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
