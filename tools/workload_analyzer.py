import json
import statistics
import sys
from pathlib import Path


SHORT_JOB_THRESHOLD = 5
LONG_JOB_THRESHOLD = 20


def load_workload(path):
    with open(path, "r") as f:
        data = json.load(f)

    if isinstance(data, list):
        return {
            "workload_name": Path(path).stem,
            "processes": data,
        }

    return data


def analyze_workload(workload):
    workload_name = workload["workload_name"]
    processes = workload["processes"]

    num_processes = len(processes)

    burst_times = [p["cpu_burst"] for p in processes]
    arrival_times = [p["arrival_time"] for p in processes]
    priorities = [p["priority"] for p in processes]

    # -------------------------------------------------
    # Basic burst statistics
    # -------------------------------------------------
    avg_burst = round(statistics.mean(burst_times), 2)
    min_burst = min(burst_times)
    max_burst = max(burst_times)

    if len(burst_times) > 1:
        burst_variance = round(
            statistics.variance(burst_times), 2
        )
    else:
        burst_variance = 0.0

    # -------------------------------------------------
    # Job classification
    # -------------------------------------------------
    short_jobs = [
        b for b in burst_times
        if b <= SHORT_JOB_THRESHOLD
    ]

    long_jobs = [
        b for b in burst_times
        if b > LONG_JOB_THRESHOLD
    ]

    short_job_ratio = round(
        len(short_jobs) / num_processes, 2
    )

    long_job_ratio = round(
        len(long_jobs) / num_processes, 2
    )

    # -------------------------------------------------
    # Interactive ratio
    # -------------------------------------------------
    interactive_count = sum(
        1 for p in processes
        if p["type"] == "interactive"
    )

    interactive_ratio = round(
        interactive_count / num_processes, 2
    )

    # -------------------------------------------------
    # Priority analysis
    # -------------------------------------------------
    priority_range = (
        max(priorities) - min(priorities)
    )

    # -------------------------------------------------
    # Arrival spread
    # -------------------------------------------------
    arrival_spread = (
        max(arrival_times) - min(arrival_times)
    )

    # -------------------------------------------------
    # Target metric heuristic
    # -------------------------------------------------
    target_metric = determine_target_metric(
        short_job_ratio,
        long_job_ratio,
        interactive_ratio
    )

    # -------------------------------------------------
    # Final summary
    # -------------------------------------------------
    summary = {
        "workload_name": workload_name,

        "num_processes": num_processes,

        "avg_burst": avg_burst,
        "min_burst": min_burst,
        "max_burst": max_burst,
        "burst_variance": burst_variance,

        "short_job_ratio": short_job_ratio,
        "long_job_ratio": long_job_ratio,

        "interactive_ratio": interactive_ratio,

        "priority_range": priority_range,

        "arrival_spread": arrival_spread,

        "target_metric": target_metric
    }

    return summary


def determine_target_metric(
    short_job_ratio,
    long_job_ratio,
    interactive_ratio
):
    """
    Heuristic for deciding
    which scheduling metric matters most.
    """

    if interactive_ratio >= 0.6:
        return "response_time"

    if short_job_ratio >= 0.6:
        return "response_time"

    if long_job_ratio >= 0.5:
        return "throughput"

    return "fairness"


def save_summary(summary, output_path):
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

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
    # Project root
    # -------------------------------------------------
    project_root = (
        Path(__file__).resolve().parent.parent
    )

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

    output_path = (
        outputs_dir / "workload_summary.json"
    )

    # -------------------------------------------------
    # Analyze workload
    # -------------------------------------------------
    workload = load_workload(input_path)

    summary = analyze_workload(workload)

    save_summary(summary, output_path)

    print(
        f"[INFO] Workload summary saved to:\n"
        f"{output_path}"
    )


if __name__ == "__main__":
    main()
