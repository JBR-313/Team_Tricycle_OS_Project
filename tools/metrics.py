import json
import statistics
import sys
from pathlib import Path


# Events with this pid are simulator-level (e.g. parameter corrections),
# not real processes, so they are skipped during per-process accounting.
SYSTEM_PID = -1

# starvation_threshold defaults to this multiple of the average waiting time.
STARVATION_MULTIPLIER = 3

# Regret/judgment thresholds (see Evaluation Plan).
SUCCESS_REGRET = 0.10
NEAR_SUCCESS_REGRET = 0.30

# Only these algorithms produce a meaningful burst prediction error.
PREDICTIVE_ALGORITHMS = ("SJF", "SRTF")

# Higher is better for these metrics; everything else is lower-is-better.
HIGHER_IS_BETTER = ("throughput",)

# Accepted aliases for recommendation.json -> canonical metric key.
TARGET_METRIC_ALIASES = {
    "response_time": "avg_response_time",
    "turnaround_time": "avg_turnaround_time",
    "waiting_time": "avg_waiting_time",
    "throughput": "throughput",
    "max_waiting_time": "max_waiting_time",
    "avg_response_time": "avg_response_time",
    "avg_turnaround_time": "avg_turnaround_time",
    "avg_waiting_time": "avg_waiting_time",
}
DEFAULT_TARGET_METRIC = "avg_response_time"

# Sub-directory under outputs/ that holds optional reference (baseline) traces.
# Any *.jsonl placed here is included in the comparison set but is never
# selected as the primary run, even if it matches argv[1].
BASELINES_SUBDIR = "baselines"

# When no external baseline trace is available, a synthetic Round-Robin
# baseline is estimated from the primary run's own process data so that
# evaluate_run() always has something to compare against.
# The estimate uses a fixed quantum (ms) as the RR time slice.
SYNTHETIC_RR_QUANTUM = 10
SYNTHETIC_BASELINE_ALGO = "_synthetic_RR"


# Alternative trace schemas name the same data differently. These aliases are
# normalized to the canonical field names on load, so both schemas work:
#   {"tick": .., "algo": ..}   (documented schema)
#   {"time": .., "algorithm": ..}  (simulator schema)
FIELD_ALIASES = {
    "time": "tick",
    "algorithm": "algo",
}


def normalize_event(ev):
    """
    Map alternative trace-schema field names onto the canonical names used
    throughout this module (e.g. "time" -> "tick", "algorithm" -> "algo").
    The canonical field wins when both are present. Returns the same dict.
    """
    for alias, canonical in FIELD_ALIASES.items():
        if canonical not in ev and alias in ev:
            ev[canonical] = ev[alias]
    return ev


def load_trace(path):
    """Read a JSONL trace file and return a list of normalized event dicts."""
    events = []

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            events.append(normalize_event(json.loads(line)))

    return events


def load_json_optional(path):
    """Return the parsed JSON at path, or None if it does not exist."""
    if not path.is_file():
        return None

    with open(path, "r") as f:
        return json.load(f)


def safe_mean(values, ndigits=2):
    """Mean over the non-null values, or None if there is nothing to average."""
    clean = [v for v in values if v is not None]

    if not clean:
        return None

    return round(float(statistics.mean(clean)), ndigits)


# -------------------------------------------------
# Per-process reconstruction
# -------------------------------------------------
def build_processes(events):
    """
    Walk the trace and rebuild each process timeline.

    Returns (procs, cpu_used) where:
      - procs[pid] holds raw timeline data plus any EXIT-reported metrics
      - cpu_used[pid] is the total CPU burst time summed from DISPATCH
        intervals (used as a fallback when EXIT does not report waiting time,
        and to estimate the waiting of processes that never complete)
    """
    procs = {}
    cpu_used = {}
    current = None  # the run in progress: {"pid", "tick", "queue"}

    def ensure(pid):
        if pid not in procs:
            procs[pid] = {
                "pid": pid,
                "arrival_time": None,
                "first_run_time": None,
                "finish_time": None,
                "exit_response": None,
                "exit_turnaround": None,
                "exit_waiting": None,
            }
            cpu_used[pid] = 0
        return procs[pid]

    for ev in events:
        pid = ev.get("pid")
        if pid is None or pid == SYSTEM_PID:
            continue

        tick = ev.get("tick")
        event = ev.get("event")

        if event == "ARRIVE":
            p = ensure(pid)
            if p["arrival_time"] is None:
                p["arrival_time"] = tick

        elif event == "DISPATCH":
            p = ensure(pid)
            if p["first_run_time"] is None:
                p["first_run_time"] = tick
            current = {
                "pid": pid,
                "tick": tick,
                "queue": ev.get("queue"),
            }

        elif event == "PREEMPT":
            ensure(pid)
            if current and current["pid"] == pid:
                cpu_used[pid] += tick - current["tick"]
                current = None

        elif event == "EXIT":
            p = ensure(pid)
            p["finish_time"] = tick

            if current and current["pid"] == pid:
                cpu_used[pid] += tick - current["tick"]
                current = None

            # EXIT-reported metrics are authoritative when present.
            if "response" in ev:
                p["exit_response"] = ev["response"]
            if "turnaround" in ev:
                p["exit_turnaround"] = ev["turnaround"]
            if "waiting" in ev:
                p["exit_waiting"] = ev["waiting"]

    return procs, cpu_used


def finalize_process(p, cpu_used):
    """
    Resolve the final per-process metrics.

    EXIT-reported values win; otherwise the metric is derived from raw
    timeline data. Anything that cannot be determined stays None (null),
    which is the case for processes that never EXIT in the trace.
    """
    arrival = p["arrival_time"]
    first_run = p["first_run_time"]
    finish = p["finish_time"]

    # response_time = first_run - arrival
    if p["exit_response"] is not None:
        response = p["exit_response"]
    elif first_run is not None and arrival is not None:
        response = first_run - arrival
    else:
        response = None

    # turnaround_time = finish - arrival
    if p["exit_turnaround"] is not None:
        turnaround = p["exit_turnaround"]
    elif finish is not None and arrival is not None:
        turnaround = finish - arrival
    else:
        turnaround = None

    # waiting_time = turnaround - total_cpu_burst_time
    if p["exit_waiting"] is not None:
        waiting = p["exit_waiting"]
    elif turnaround is not None:
        waiting = turnaround - cpu_used
    else:
        waiting = None

    return {
        "pid": p["pid"],
        "arrival_time": arrival,
        "first_run_time": first_run,
        "finish_time": finish,
        "response_time": response,
        "turnaround_time": turnaround,
        "waiting_time": waiting,
    }


# -------------------------------------------------
# Scheduler parameter inference
# -------------------------------------------------
def infer_params(events):
    """
    Best-effort reconstruction of the scheduler parameters from the trace.

      - queues:          highest observed queue index + 1
      - quantum:         per-queue time slice inferred from the duration of
                         runs that ended with reason "quantum_expired"
                         (None for queues with no such evidence)
      - aging_threshold: latest value seen in a CORRECTION_APPLIED event
      - boost_interval:  not observable from the trace -> None
    """
    queue_ids = set()
    quantum_samples = {}  # queue -> [durations]
    aging_threshold = None
    current = None

    for ev in events:
        event = ev.get("event")

        for key in ("queue", "from_queue", "to_queue"):
            if isinstance(ev.get(key), int):
                queue_ids.add(ev[key])

        if event == "DISPATCH":
            current = {
                "pid": ev.get("pid"),
                "tick": ev.get("tick"),
                "queue": ev.get("queue"),
            }

        elif event in ("PREEMPT", "EXIT"):
            if current and current["pid"] == ev.get("pid"):
                if (
                    event == "PREEMPT"
                    and ev.get("reason") == "quantum_expired"
                    and isinstance(current["queue"], int)
                ):
                    duration = ev.get("tick") - current["tick"]
                    quantum_samples.setdefault(
                        current["queue"], []
                    ).append(duration)
                current = None

        elif event == "CORRECTION_APPLIED":
            new_params = ev.get("new_params") or {}
            if "aging_threshold" in new_params:
                aging_threshold = new_params["aging_threshold"]

    queues = (max(queue_ids) + 1) if queue_ids else 0

    quantum = []
    for q in range(queues):
        samples = quantum_samples.get(q)
        quantum.append(max(samples) if samples else None)

    return {
        "queues": queues,
        "quantum": quantum,
        "aging_threshold": aging_threshold,
        "boost_interval": None,
    }


# -------------------------------------------------
# Starvation
# -------------------------------------------------
def evaluate_starvation(per_process, cpu_used, avg_waiting_time, makespan):
    """
    A process starves when it waits longer than the starvation threshold
    (default: 3x the average waiting time of completed processes).

      - completed processes are judged by their final waiting_time
      - processes that never completed are judged by their waiting so far,
        i.e. makespan - arrival - cpu_used (this catches a process that was
        starved badly enough that it never got to finish)
    """
    if avg_waiting_time is None or avg_waiting_time <= 0:
        return False, [], None

    threshold = STARVATION_MULTIPLIER * avg_waiting_time
    starving = []

    for p in per_process:
        pid = p["pid"]

        if p["finish_time"] is not None:
            waited = p["waiting_time"]
        elif p["arrival_time"] is not None:
            waited = makespan - p["arrival_time"] - cpu_used.get(pid, 0)
        else:
            waited = None

        if waited is not None and waited > threshold:
            starving.append(pid)

    return bool(starving), sorted(starving), round(float(threshold), 2)


# -------------------------------------------------
# Regret / judgment
# -------------------------------------------------
def resolve_target_metric(recommendation):
    raw = DEFAULT_TARGET_METRIC
    if recommendation and recommendation.get("target_metric"):
        raw = recommendation["target_metric"]
    return TARGET_METRIC_ALIASES.get(raw, DEFAULT_TARGET_METRIC)


# Workload files live under this directory relative to the project root.
WORKLOAD_DIR = "workloads"


def resolve_workload_file(recommendation):
    """
    Resolve the workload file path from recommendation.json.

    The name is taken, in order, from:
      - recommendation["workload_file"]
      - recommendation["workload_interpretation"]["workload_file"]
      - recommendation["workload_interpretation"]["workload_type"]
        (a bare type like "interactive_heavy" names the matching workload)

    The result is normalised to a "workloads/<name>.json" path: a missing
    ".json" extension is added, and a bare file name (no directory) is placed
    under the workloads/ directory. An explicit path is left untouched.

    Returns None when recommendation.json is absent or carries none of these.
    """
    if not recommendation:
        return None

    name = recommendation.get("workload_file")
    if not name:
        interp = recommendation.get("workload_interpretation") or {}
        name = interp.get("workload_file") or interp.get("workload_type")

    if not name:
        return None

    if not name.endswith(".json"):
        name = f"{name}.json"

    name = name.replace("\\", "/")
    if "/" not in name:
        name = f"{WORKLOAD_DIR}/{name}"

    return name


def compute_regret(target_metric, llm_metric, baseline):
    """
    regret_score = normalised distance from the best algorithm on the
    target metric, where 0.0 means "matched the best".

    The Evaluation Plan writes the formula as (best - llm) / best, which is
    only correctly signed for higher-is-better metrics (throughput). For the
    default lower-is-better metrics we use (llm - best) / best so that a worse
    result yields a positive regret, keeping the judgment thresholds coherent.

    Needs at least one comparison algorithm (the mandatory RR baseline), so it
    returns None when no baseline data is available.
    """
    if llm_metric is None or not baseline:
        return None

    higher_better = target_metric in HIGHER_IS_BETTER

    values = [llm_metric]
    for algo_metrics in baseline.values():
        if isinstance(algo_metrics, dict):
            v = algo_metrics.get(target_metric)
        else:
            v = algo_metrics  # baseline given as {algo: value}
        if v is not None:
            values.append(v)

    if len(values) < 2:
        return None

    best = max(values) if higher_better else min(values)

    if best == 0:
        return 0.0 if llm_metric == 0 else None

    if higher_better:
        regret = (best - llm_metric) / best
    else:
        regret = (llm_metric - best) / best

    return round(max(regret, 0.0), 3)


def compute_judgment(regret_score, starvation_occurred):
    # Starvation is an immediate FAIL regardless of regret.
    if starvation_occurred:
        return "FAIL"
    if regret_score is None:
        return "UNKNOWN"
    if regret_score <= SUCCESS_REGRET:
        return "SUCCESS"
    if regret_score <= NEAR_SUCCESS_REGRET:
        return "NEAR-SUCCESS"
    return "FAIL"


def pick_best_algorithm(all_metrics, target_metric):
    """
    Return the algorithm name with the best value on target_metric across the
    evaluated runs (max for higher-is-better metrics, min otherwise).

    all_metrics maps algo -> its metrics dict. Returns None when no run has a
    value for the metric.
    """
    higher_better = target_metric in HIGHER_IS_BETTER

    candidates = [
        (algo, m.get(target_metric))
        for algo, m in all_metrics.items()
        if m.get(target_metric) is not None
    ]
    if not candidates:
        return None

    chooser = max if higher_better else min
    return chooser(candidates, key=lambda item: item[1])[0]


def compute_burst_prediction_error(events, algorithm):
    """
    Mean |predicted_burst - actual_burst| over every (process, burst) pair.
    Only meaningful for SJF/SRTF runs that recorded predictor data; otherwise
    returns None.
    """
    if algorithm not in PREDICTIVE_ALGORITHMS:
        return None

    errors = []
    for ev in events:
        predicted = ev.get("predicted_burst")
        actual = ev.get("actual_burst")
        if predicted is not None and actual is not None:
            errors.append(abs(predicted - actual))

    if not errors:
        return None

    return round(float(statistics.mean(errors)), 2)


# -------------------------------------------------
# Aggregate metrics
# -------------------------------------------------
def compute_metrics(events, recommendation=None):
    procs_raw, cpu_used = build_processes(events)

    per_process = [
        finalize_process(p, cpu_used[pid])
        for pid, p in sorted(procs_raw.items())
    ]

    # -------------------------------------------------
    # Simulation span (makespan)
    # -------------------------------------------------
    ticks = [
        ev["tick"] for ev in events
        if isinstance(ev.get("tick"), int)
    ]
    total_execution_time = (max(ticks) - min(ticks)) if ticks else 0

    # -------------------------------------------------
    # Completed vs. incomplete processes
    #   Metrics are averaged over completed processes only; processes that
    #   never finished are excluded.
    # -------------------------------------------------
    completed = [p for p in per_process if p["finish_time"] is not None]

    process_count = len(per_process)
    completed_count = len(completed)

    preemption_count = sum(
        1 for ev in events if ev.get("event") == "PREEMPT"
    )

    # -------------------------------------------------
    # Timing aggregates (completed processes only)
    # -------------------------------------------------
    waiting_clean = [
        p["waiting_time"] for p in completed
        if p["waiting_time"] is not None
    ]

    avg_response_time = safe_mean(p["response_time"] for p in completed)
    avg_turnaround_time = safe_mean(p["turnaround_time"] for p in completed)
    avg_waiting_time = safe_mean(p["waiting_time"] for p in completed)
    max_waiting_time = max(waiting_clean) if waiting_clean else None

    throughput = (
        round(completed_count / total_execution_time, 3)
        if total_execution_time else 0.0
    )

    # -------------------------------------------------
    # Scheduling algorithm label
    # -------------------------------------------------
    algos = [ev.get("algo") for ev in events if ev.get("algo")]
    scheduling_algorithm = algos[0] if algos else None

    # -------------------------------------------------
    # Starvation
    # -------------------------------------------------
    starvation_occurred, starvation_pids, _threshold = evaluate_starvation(
        per_process, cpu_used, avg_waiting_time, total_execution_time
    )

    # Some traces emit explicit STARVATION_WARNING events; these are
    # authoritative and are merged with (and can override) the heuristic above.
    flagged = sorted({
        ev.get("pid") for ev in events
        if ev.get("event") == "STARVATION_WARNING"
        and isinstance(ev.get("pid"), int) and ev.get("pid") != SYSTEM_PID
    })
    if flagged:
        starvation_occurred = True
        starvation_pids = sorted(set(starvation_pids) | set(flagged))

    # -------------------------------------------------
    # Regret / judgment
    #   regret_score and best_algorithm need a cross-algorithm comparison and
    #   are filled in by evaluate_run() once every trace has been computed.
    #   Here we only seed a starvation-aware judgment (FAIL on starvation,
    #   otherwise UNKNOWN until a comparison is available).
    # -------------------------------------------------
    regret_score = None
    best_algorithm = None
    judgment = compute_judgment(regret_score, starvation_occurred)

    # -------------------------------------------------
    # Workload file (from recommendation.json; derived from the workload
    # type when no explicit file name is provided)
    # -------------------------------------------------
    workload_file = resolve_workload_file(recommendation)

    # -------------------------------------------------
    # Final metrics
    # -------------------------------------------------
    metrics = {
        "scheduling_algorithm": scheduling_algorithm,
        "params": infer_params(events),
        "process_count": process_count,
        "completed_count": completed_count,
        "total_execution_time": total_execution_time,
        "avg_response_time": avg_response_time,
        "avg_turnaround_time": avg_turnaround_time,
        "avg_waiting_time": avg_waiting_time,
        "throughput": throughput,
        "max_waiting_time": max_waiting_time,
        "starvation_occurred": starvation_occurred,
        "starvation_pids": starvation_pids,
        "preemption_count": preemption_count,
        "per_process": per_process,
        "judgment": judgment,
        "regret_score": regret_score,
        "best_algorithm": best_algorithm,
        "workload_file": workload_file,
    }

    return metrics


def evaluate_run(primary, baseline, all_metrics, target_metric):
    """
    Fill in the comparison-dependent fields on the primary run's metrics:
    best_algorithm, regret_score and the final judgment.

      - best_algorithm: best performer on target_metric across all runs
                        (including the primary itself)
      - regret_score:   primary's normalised distance from the best, computed
                        against the other algorithms in `baseline`
                        (None when there is nothing to compare against)
      - judgment:       re-derived from regret_score, with starvation still
                        forcing an immediate FAIL

    Mutates and returns `primary`.
    """
    primary["best_algorithm"] = pick_best_algorithm(all_metrics, target_metric)
    primary["regret_score"] = compute_regret(
        target_metric, primary.get(target_metric), baseline
    )
    primary["judgment"] = compute_judgment(
        primary["regret_score"], primary["starvation_occurred"]
    )
    return primary


def save_metrics(metrics, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(metrics, f, indent=2)


def _select_primary(runs, recommendation, explicit, outputs_dir):
    """
    Pick the (algo, metrics) run to report on, in priority order:
      1. the explicit trace passed on the command line
      2. recommendation.json's recommended_scheduling_algorithm
      3. outputs/trace.jsonl
      4. the first run found
    """
    if explicit:
        target = explicit.resolve()
        for path, algo, m in runs:
            if path.resolve() == target:
                return algo, m

    if recommendation:
        rec_algo = recommendation.get("recommended_scheduling_algorithm")
        if rec_algo:
            for _, algo, m in runs:
                if algo == rec_algo:
                    return algo, m

    default_path = (outputs_dir / "trace.jsonl").resolve()
    for path, algo, m in runs:
        if path.resolve() == default_path:
            return algo, m

    return runs[0][1], runs[0][2]


def _make_synthetic_rr_baseline(primary_metrics):
    """
    Estimate Round-Robin metrics from the primary run's per-process data.

    This is used as a last-resort baseline when no external trace file is
    available, so that evaluate_run() always receives a non-empty comparison
    set and regret_score / best_algorithm are never left as None.

    The estimate is deliberately conservative (simple uniform time-slice
    simulation), so any real RR trace would override it automatically.

    Returns a metrics-dict keyed to SYNTHETIC_BASELINE_ALGO, or None when
    not enough process data is available to build a meaningful estimate.
    """
    per_process = primary_metrics.get("per_process") or []
    total_time = primary_metrics.get("total_execution_time") or 0

    if not per_process or not total_time:
        return None

    q = SYNTHETIC_RR_QUANTUM

    # Collect (arrival, burst) for processes that have both.
    tasks = []
    for p in per_process:
        arrival = p.get("arrival_time")
        turnaround = p.get("turnaround_time")
        waiting = p.get("waiting_time")
        if arrival is None or turnaround is None:
            continue
        burst = turnaround - (waiting or 0)
        if burst <= 0:
            continue
        tasks.append({"arrival": arrival, "burst": burst})

    if not tasks:
        return None

    # Simple RR simulation on the inferred tasks.
    tasks = sorted(tasks, key=lambda t: t["arrival"])
    ready = []
    clock = 0
    task_state = [{"remaining": t["burst"], "arrival": t["arrival"],
                   "first_run": None, "finish": None} for t in tasks]
    idx = 0  # next un-arrived task pointer

    response_times = []
    turnaround_times = []
    waiting_times = []

    while True:
        # Enqueue newly arrived tasks.
        while idx < len(task_state) and task_state[idx]["arrival"] <= clock:
            ready.append(idx)
            idx += 1

        if not ready:
            if idx >= len(task_state):
                break
            # Advance clock to next arrival.
            clock = task_state[idx]["arrival"]
            continue

        i = ready.pop(0)
        ts = task_state[i]

        if ts["first_run"] is None:
            ts["first_run"] = clock

        run = min(q, ts["remaining"])
        clock += run
        ts["remaining"] -= run

        # Enqueue any tasks that arrived during this slice.
        while idx < len(task_state) and task_state[idx]["arrival"] <= clock:
            ready.append(idx)
            idx += 1

        if ts["remaining"] <= 0:
            ts["finish"] = clock
            arrival = tasks[i]["arrival"]
            burst = tasks[i]["burst"]
            tat = ts["finish"] - arrival
            wt = tat - burst
            rt = ts["first_run"] - arrival
            turnaround_times.append(tat)
            waiting_times.append(wt)
            response_times.append(rt)
        else:
            ready.append(i)

    if not turnaround_times:
        return None

    completed = len(turnaround_times)
    throughput = round(completed / total_time, 3) if total_time else 0.0

    return {
        "scheduling_algorithm": SYNTHETIC_BASELINE_ALGO,
        "avg_response_time": safe_mean(response_times),
        "avg_turnaround_time": safe_mean(turnaround_times),
        "avg_waiting_time": safe_mean(waiting_times),
        "max_waiting_time": round(float(max(waiting_times)), 2) if waiting_times else None,
        "throughput": throughput,
        "starvation_occurred": False,
        "_synthetic": True,
    }


def main():
    # -------------------------------------------------
    # Project root
    # -------------------------------------------------
    project_root = Path(__file__).resolve().parent.parent
    outputs_dir = project_root / "outputs"

    # -------------------------------------------------
    # Recommendation (target metric + recommended algorithm + workload)
    # -------------------------------------------------
    recommendation = load_json_optional(outputs_dir / "recommendation.json")
    target_metric = resolve_target_metric(recommendation)

    # -------------------------------------------------
    # Comparison set: every *.jsonl in outputs/ **and** outputs/baselines/ is
    #   one algorithm run.  An explicit trace may be passed as argv[1].
    #   Traces in baselines/ are never selected as the primary run.
    # -------------------------------------------------
    explicit = Path(sys.argv[1]) if len(sys.argv) >= 2 else None

    primary_trace_paths = sorted(outputs_dir.glob("*.jsonl"))
    baseline_trace_paths = sorted(
        (outputs_dir / BASELINES_SUBDIR).glob("*.jsonl")
    )

    if explicit and explicit.resolve() not in {
        p.resolve() for p in primary_trace_paths + baseline_trace_paths
    }:
        primary_trace_paths.insert(0, explicit)

    all_trace_paths = primary_trace_paths + baseline_trace_paths

    if not all_trace_paths:
        print(f"[ERROR] No trace files found in: {outputs_dir}")
        sys.exit(1)

    # Compute base metrics for every algorithm run.
    runs = []           # (path, algo, metrics, is_baseline_only)
    for tp in all_trace_paths:
        if not tp.is_file():
            print(f"[WARN] Skipping missing trace: {tp}")
            continue
        events = load_trace(tp)
        m = compute_metrics(events, recommendation)
        algo = m["scheduling_algorithm"] or tp.stem
        is_baseline_only = tp in baseline_trace_paths
        runs.append((tp, algo, m, is_baseline_only))

    if not runs:
        print("[ERROR] No readable trace files.")
        sys.exit(1)

    # -------------------------------------------------
    # Pick the primary (LLM-evaluated) run, then compare it against the rest.
    #   all_metrics -> determines best_algorithm (primary included)
    #   baseline    -> the other algorithms, used for regret_score
    # -------------------------------------------------
    # _select_primary only considers non-baseline-only runs.
    primary_runs = [(p, a, m) for p, a, m, b in runs if not b]
    if not primary_runs:
        print("[ERROR] No primary (non-baseline) trace files found.")
        sys.exit(1)

    primary_algo, primary_metrics = _select_primary(
        primary_runs, recommendation, explicit, outputs_dir
    )

    all_metrics = {}
    baseline = {}
    for _, algo, m, _ in runs:
        all_metrics.setdefault(algo, m)
        if algo != primary_algo:
            baseline.setdefault(algo, m)

    # -------------------------------------------------
    # Synthetic baseline fallback: when no external comparison algorithm
    #   exists, estimate RR metrics from the primary run's process data so
    #   that regret_score and best_algorithm are always populated.
    # -------------------------------------------------
    if not baseline:
        synth = _make_synthetic_rr_baseline(primary_metrics)
        if synth:
            baseline[SYNTHETIC_BASELINE_ALGO] = synth
            all_metrics[SYNTHETIC_BASELINE_ALGO] = synth
            print(
                "[INFO] No external baseline traces found – using a synthetic "
                f"Round-Robin estimate ({SYNTHETIC_BASELINE_ALGO}) so that "
                "regret_score and best_algorithm can be computed.\n"
                f"       Add *.jsonl files to outputs/{BASELINES_SUBDIR}/ "
                "for a real comparison."
            )

    evaluate_run(primary_metrics, baseline, all_metrics, target_metric)

    # -------------------------------------------------
    # Save the primary run's metrics.
    # -------------------------------------------------
    output_path = outputs_dir / "metrics.json"
    save_metrics(primary_metrics, output_path)

    real_baseline = {k: v for k, v in baseline.items()
                     if not (isinstance(v, dict) and v.get("_synthetic"))}
    compared = ", ".join(sorted(real_baseline)) or f"(none – used {SYNTHETIC_BASELINE_ALGO})"
    print(f"[INFO] Metrics saved to:\n{output_path}")
    print(f"[INFO] Evaluated algorithm: {primary_algo}")
    print(f"[INFO] Compared against:    {compared}")
    print(f"[INFO] Best ({target_metric}): {primary_metrics['best_algorithm']}")
    print(f"[INFO] Regret score:        {primary_metrics['regret_score']}")
    print(f"[INFO] Judgment:            {primary_metrics['judgment']}")

    if not real_baseline and not baseline:
        print(
            "[WARN] Only one algorithm was found and synthetic RR estimation "
            "failed (insufficient process data). Add more *.jsonl trace files "
            f"to outputs/ or outputs/{BASELINES_SUBDIR}/ for a meaningful "
            "comparison."
        )


if __name__ == "__main__":
    main()
