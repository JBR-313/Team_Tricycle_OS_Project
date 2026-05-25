import json
import statistics
import sys
from pathlib import Path

STARVATION_PRIORITY_RATIO = 3

def load_workload(path):
    with open(path, "r") as f:
        data = json.load(f)

    if isinstance(data, list):
        return {
            "workload_name": Path(path).stem,
            "processes": data,
        }

    return data


# ---------------------------------------------------------
# Per-process helpers
# ---------------------------------------------------------

def total_cpu_burst_time(process):
    """Sum of all CPU burst durations for one process."""
    return sum(process["cpu_bursts"])


def burst_count(process):
    """Number of CPU bursts (= scheduling phases)."""
    return len(process["cpu_bursts"])


# ---------------------------------------------------------
# Main analysis
# ---------------------------------------------------------

def analyze_workload(workload, input_path: Path):
    processes = workload["processes"]
    n = len(processes)

    arrival_times  = [p["arrival_time"] for p in processes]
    priorities     = [p["priority"]     for p in processes]
    labels         = [p.get("label", p.get("type", "unknown"))
                      for p in processes]

    # Per-process total CPU work
    cpu_works = [total_cpu_burst_time(p) for p in processes]

    # Per-process burst counts
    burst_counts = [burst_count(p) for p in processes]

    # -------------------------------------------------
    # avg_arrival_gap
    # Mean gap between consecutive arrival times.
    # Requires sorted arrivals; returns 0.0 for n <= 1.
    # -------------------------------------------------
    sorted_arrivals = sorted(arrival_times)
    if n > 1:
        gaps = [
            sorted_arrivals[i + 1] - sorted_arrivals[i]
            for i in range(n - 1)
        ]
        avg_arrival_gap = round(statistics.mean(gaps), 2)
    else:
        avg_arrival_gap = 0.0

    # -------------------------------------------------
    # Label ratios
    # -------------------------------------------------
    cpu_bound_count   = sum(1 for l in labels if l == "cpu_bound")
    interactive_count = sum(1 for l in labels if l == "interactive")

    cpu_bound_ratio   = round(cpu_bound_count   / n, 2)
    interactive_ratio = round(interactive_count / n, 2)

    # -------------------------------------------------
    # Priority statistics
    # -------------------------------------------------
    avg_priority = round(statistics.mean(priorities), 2)

    if n > 1:
        priority_variance = round(
            statistics.variance(priorities), 2
        )
    else:
        priority_variance = 0.0

    # -------------------------------------------------
    # Starvation risk heuristic
    # A low-priority process risks starvation when the
    # priority range is wide AND high-priority processes
    # keep arriving to preempt it.
    # -------------------------------------------------
    priority_min = min(priorities)
    priority_max = max(priorities)

    has_starvation_risk = (
        priority_max >= priority_min * STARVATION_PRIORITY_RATIO
        and n > 1
    )

    # -------------------------------------------------
    # Burst count distribution
    # -------------------------------------------------
    burst_count_distribution = {
        "min": min(burst_counts),
        "max": max(burst_counts),
        "avg": round(statistics.mean(burst_counts), 2),
    }

    # -------------------------------------------------
    # Total CPU work across all processes
    # -------------------------------------------------
    total_cpu_work = sum(cpu_works)

    # -------------------------------------------------
    # Resolve workload_file relative label
    # (show path from project root if possible,
    #  otherwise use the absolute path string)
    # -------------------------------------------------
    try:
        project_root  = input_path.resolve().parent.parent
        workload_file = str(
            input_path.resolve().relative_to(project_root)
        )
    except ValueError:
        workload_file = str(input_path.resolve())

    # -------------------------------------------------
    # Final summary
    # -------------------------------------------------
    summary = {
        "process_count":             n,
        "avg_arrival_gap":           avg_arrival_gap,
        "cpu_bound_ratio":           cpu_bound_ratio,
        "interactive_ratio":         interactive_ratio,
        "avg_priority":              avg_priority,
        "priority_variance":         priority_variance,
        "has_starvation_risk":       has_starvation_risk,
        "burst_count_distribution":  burst_count_distribution,
        "total_cpu_work":            total_cpu_work,
        "workload_file":             workload_file,
    }

    return summary


def save_summary(summary, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(summary, f, indent=4)


def main():
    if len(sys.argv) != 2:
        print(
            "Usage: python workload_analyzer.py "
            "<workload.json>"
        )
        sys.exit(1)

    # -------------------------------------------------
    # Project root  (<root>/src/workload_analyzer.py)
    # -------------------------------------------------
    project_root = Path(__file__).resolve().parent.parent

    # -------------------------------------------------
    # Input workload path
    # -------------------------------------------------
    workloads_dir = project_root / "workloads"

    input_arg = Path(sys.argv[1])

    if input_arg.is_file():
        input_path = input_arg
    else:
        input_path = workloads_dir / input_arg.name

    if not input_path.is_file():
        print(
            f"[ERROR] Workload file not found: "
            f"{input_path}"
        )
        sys.exit(1)

    # -------------------------------------------------
    # Output path
    # -------------------------------------------------
    outputs_dir = project_root / "outputs"
    output_path = outputs_dir / "workload_summary.json"

    # -------------------------------------------------
    # Run analysis
    # -------------------------------------------------
    workload = load_workload(input_path)
    summary  = analyze_workload(workload, input_path)
    save_summary(summary, output_path)

    print(
        f"[INFO] Workload summary saved to:\n"
        f"{output_path}"
    )


if __name__ == "__main__":
    main()
