#!/usr/bin/env python3
"""Multi-seed robustness sweep — turns single-point results into statistics.

A single simulator run is one sample: it proves an algorithm won *that*
jittered instance, not that it wins *the workload*. This tool runs the same
workload across many seeds (each seed re-jitters arrivals/bursts via
tools/workload_jitter.py) and reports, per algorithm:

  - the target metric's mean ± standard deviation (and min/max) across seeds
  - how often each algorithm was the best (best-algorithm frequency)
  - ranking stability: the fraction of seeds the most-frequent winner actually
    won

That lets a recommendation be defended as "MLFQ wins 9/10 seeds, avg_response
4.1 ± 0.3" instead of "MLFQ won the one run we showed". Seed-jitter is a
SIMULATOR concept (xv6 is deterministic-by-profile), so this sweep is
simulator-only by construction — the same honesty boundary as the orchestrator.

Usage:
    python3 tools/seed_sweep.py --workload ambiguous_mixed --seeds 1-20
    python3 tools/seed_sweep.py --workload workloads/short_jobs_clustered.json \
        --seeds 1-50 --metric avg_waiting_time
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import statistics
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from workload_jitter import jitter_workload          # noqa: E402
from scheduler_simulator import load_processes, run_all_algorithms  # noqa: E402
from schema_compat import normalize_target_metric, is_higher_better_metric  # noqa: E402

OUT_DIR = PROJECT_ROOT / "outputs" / "seed_sweep"
WORKLOADS_DIR = PROJECT_ROOT / "workloads"

# Algorithms appear in metrics["comparison"] under these display names.
COMPARISON_ALGOS = ["RR", "FCFS", "Priority", "MLFQ", "SJF", "SRTF"]


def _profile_map() -> dict:
    """The orchestrator's canonical profile→file map, so this sweep accepts the
    exact same names the dashboard and pipeline use (e.g. short_jobs_clustered).
    Falls back to {} if the orchestrator cannot be imported."""
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from orchestrator import PROFILE_MAP  # noqa: E402
        return dict(PROFILE_MAP)
    except Exception:
        return {}


def resolve_workload(name_or_path: str) -> Path:
    """Accept a file path, an orchestrator profile alias, or a bare stem in
    workloads/. Aliases are resolved via the orchestrator's PROFILE_MAP so the
    same names work here as in the dashboard / pipeline."""
    p = Path(name_or_path)
    if p.is_file():
        return p
    pm = _profile_map()
    if name_or_path in pm and Path(pm[name_or_path]).is_file():
        return Path(pm[name_or_path])
    cand = WORKLOADS_DIR / f"{name_or_path}.json"
    if cand.is_file():
        return cand
    known = ", ".join(sorted(pm)) if pm else "(profile map unavailable)"
    raise FileNotFoundError(
        f"workload not found: {name_or_path} (tried {cand}). Known profiles: {known}")


def parse_seeds(spec: str) -> list[int]:
    """Parse "1-20" (inclusive range) or "1,4,9" (explicit list)."""
    spec = spec.strip()
    if "-" in spec and "," not in spec:
        lo, hi = spec.split("-", 1)
        lo, hi = int(lo), int(hi)
        if hi < lo:
            lo, hi = hi, lo
        return list(range(lo, hi + 1))
    return [int(x) for x in spec.split(",") if x.strip()]


def _stats(values: list[float]) -> dict:
    """mean / std / min / max for a list of metric samples (std=0 when n<2)."""
    clean = [v for v in values if isinstance(v, (int, float))]
    if not clean:
        return {"mean": None, "std": None, "min": None, "max": None, "n": 0}
    return {
        "mean": round(statistics.fmean(clean), 4),
        "std": round(statistics.stdev(clean), 4) if len(clean) > 1 else 0.0,
        "min": round(min(clean), 4),
        "max": round(max(clean), 4),
        "n": len(clean),
    }


def run(workload_path: Path, seeds: list[int], metric: str | None) -> dict:
    base = json.loads(workload_path.read_text(encoding="utf-8"))
    base_target = base.get("target_metric") if isinstance(base, dict) else None
    target = normalize_target_metric(metric or base_target or "avg_response_time")
    higher = is_higher_better_metric(target)

    # Per-algorithm sample lists of the target metric, and best-algo tally.
    per_algo_values: dict[str, list[float]] = {a: [] for a in COMPARISON_ALGOS}
    best_tally: dict[str, int] = {}
    per_seed: list[dict] = []

    with tempfile.TemporaryDirectory(prefix="seed_sweep_") as tmp:
        scratch_dir = Path(tmp)
        scratch_wl = scratch_dir / "instance.json"
        for seed in seeds:
            jittered = jitter_workload(base, seed)
            scratch_wl.write_text(json.dumps(jittered), encoding="utf-8")
            processes = load_processes(scratch_wl)
            # run_all_algorithms prints a per-algo line per call; silence it so a
            # 20-seed sweep does not emit 120 lines of per-run noise.
            with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
                metrics = run_all_algorithms(
                    processes, guard_params={}, rec_algo="RR",
                    out_dir=scratch_dir, target_metric=target,
                )
            comparison = metrics.get("comparison", {})
            seed_vals: dict[str, float] = {}
            for algo in COMPARISON_ALGOS:
                v = comparison.get(algo, {}).get(target)
                if isinstance(v, (int, float)):
                    per_algo_values[algo].append(v)
                    seed_vals[algo] = v
            best = metrics.get("best_algorithm")
            if best:
                best_tally[best] = best_tally.get(best, 0) + 1
            per_seed.append({"seed": seed, "best_algorithm": best, "values": seed_vals})

    # Aggregate per algorithm.
    per_algorithm = {}
    for algo in COMPARISON_ALGOS:
        vals = per_algo_values[algo]
        if not vals:
            continue
        per_algorithm[algo] = {
            "target": _stats(vals),
            "best_count": best_tally.get(algo, 0),
        }

    most_frequent_best = max(best_tally, key=best_tally.get) if best_tally else None
    stability = (round(best_tally[most_frequent_best] / len(seeds), 3)
                 if most_frequent_best and seeds else None)

    return {
        "workload": workload_path.stem,
        "target_metric": target,
        "higher_is_better": higher,
        "seed_count": len(seeds),
        "seeds": seeds,
        "per_algorithm": per_algorithm,
        "best_algorithm_distribution": best_tally,
        "most_frequent_best": most_frequent_best,
        "ranking_stability": stability,
        "interpretation": (
            f"{most_frequent_best} was best in {best_tally.get(most_frequent_best, 0)}"
            f"/{len(seeds)} jittered instances"
            if most_frequent_best else "no winner could be determined"
        ),
        "per_seed": per_seed,
        "_note": ("Seed-jitter is simulator-only; xv6 is deterministic-by-profile. "
                  "std=0 for an algorithm means the metric did not vary across seeds."),
    }


def render_markdown(result: dict) -> str:
    target = result["target_metric"]
    arrow = "higher=better" if result["higher_is_better"] else "lower=better"
    lines = [
        f"# Seed sweep — {result['workload']}",
        "",
        f"- target metric: **{target}** ({arrow})",
        f"- seeds: {result['seed_count']} "
        f"({result['seeds'][0]}–{result['seeds'][-1]})" if result["seeds"] else "- seeds: 0",
        f"- ranking stability: **{result['interpretation']}**"
        + (f" → {round(result['ranking_stability'] * 100)}% of seeds"
           if result["ranking_stability"] is not None else ""),
        "",
        f"| algorithm | {target} mean ± std | min | max | best in N seeds |",
        "|---|---|---|---|---|",
    ]
    pa = result["per_algorithm"]
    # Sort by mean (best first per metric direction).
    def _key(item):
        m = item[1]["target"]["mean"]
        return (m if m is not None else float("inf"))
    ordered = sorted(pa.items(), key=_key, reverse=result["higher_is_better"])
    for algo, info in ordered:
        t = info["target"]
        mark = " ⭐" if algo == result["most_frequent_best"] else ""
        lines.append(
            f"| {algo}{mark} | {t['mean']} ± {t['std']} | {t['min']} | {t['max']} "
            f"| {info['best_count']} |"
        )
    lines += ["", f"_{result['_note']}_", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Multi-seed robustness sweep (simulator-only)")
    ap.add_argument("--workload", required=True,
                    help="profile name (looked up in workloads/) or a .json path")
    ap.add_argument("--seeds", default="1-20",
                    help='seed range "1-20" or explicit list "1,4,9" (default 1-20)')
    ap.add_argument("--metric", default=None,
                    help="target metric to aggregate (default: workload's target_metric)")
    args = ap.parse_args()

    try:
        wl_path = resolve_workload(args.workload)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    seeds = parse_seeds(args.seeds)
    if not seeds:
        print("ERROR: no seeds parsed", file=sys.stderr)
        return 1

    print(f"[seed_sweep] {wl_path.stem}: {len(seeds)} seeds "
          f"({seeds[0]}..{seeds[-1]})")
    result = run(wl_path, seeds, args.metric)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / f"seed_sweep_{wl_path.stem}.json"
    md_path = OUT_DIR / f"seed_sweep_{wl_path.stem}.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    print(f"[seed_sweep] {result['interpretation']}")
    print(f"[seed_sweep] wrote {json_path}")
    print(f"[seed_sweep] wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
