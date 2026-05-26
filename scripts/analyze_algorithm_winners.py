#!/usr/bin/env python3
"""analyze_algorithm_winners.py — verifiable per-profile per-metric best table.

Reads the committed snapshot data under
``dashboard_live/public/live-data/snapshots/<profile>/metrics.json``
and prints, for each profile and each canonical metric, which
scheduling algorithm scored best. No data mutation, no LLM call.

Companion to ``docs/algorithm_decision_diversity_audit.md`` — keeps
the audit's §2 table reproducible from current snapshots as the data
evolves.

Usage:
    python3 scripts/analyze_algorithm_winners.py
    python3 scripts/analyze_algorithm_winners.py --dir dashboard_live/public/live-data/snapshots
    python3 scripts/analyze_algorithm_winners.py --json   # machine-readable

Exit:
    0 — at least one profile produced a usable comparison row.
    1 — no snapshots found / no parsable metrics.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "dashboard_live" / "public" / "live-data" / "snapshots"

METRICS = [
    ("avg_response_time", False, "resp"),
    ("avg_waiting_time", False, "wait"),
    ("avg_turnaround_time", False, "turn"),
    ("throughput", True, "thru"),
    ("max_waiting_time", False, "max_w"),
    ("preemption_count", False, "preempt"),
]


def _load(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def best_for(metric: str, higher_better: bool, comparison: dict) -> tuple[str | None, float | None]:
    """Return (algo, value) for the best entry on `metric`, or (None, None)."""
    candidates: list[tuple[str, float]] = []
    for algo, row in comparison.items():
        if not isinstance(row, dict):
            continue
        v = row.get(metric)
        if isinstance(v, (int, float)):
            candidates.append((algo, float(v)))
    if not candidates:
        return None, None
    return (max if higher_better else min)(candidates, key=lambda x: x[1])


def collect(root: Path) -> list[dict]:
    """Return one entry per <profile>/ sub-directory under root."""
    if not root.is_dir():
        return []
    entries: list[dict] = []
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        m = _load(sub / "metrics.json")
        if not m:
            entries.append({"profile": sub.name, "error": "metrics.json not parseable"})
            continue
        cmp = m.get("comparison") or {}
        if not cmp:
            entries.append({"profile": sub.name, "error": "no comparison block"})
            continue
        per_metric: dict[str, dict] = {}
        for metric, higher, _ in METRICS:
            best_algo, best_val = best_for(metric, higher, cmp)
            if best_algo is None:
                continue
            per_metric[metric] = {
                "best_algo": best_algo,
                "best_val": best_val,
                "higher_better": higher,
            }
        entries.append({
            "profile": sub.name,
            "selected": m.get("scheduling_algorithm"),
            "judgment": m.get("judgment"),
            "regret_score": m.get("regret_score"),
            "starvation_occurred": m.get("starvation_occurred"),
            "best_per_metric": per_metric,
        })
    return entries


def print_table(entries: list[dict]) -> None:
    header_cols = ["profile", "selected"] + [short for (_, _, short) in METRICS]
    widths = [22, 10] + [10] * len(METRICS)
    line = "  ".join(c.ljust(w) for c, w in zip(header_cols, widths))
    print(line)
    print("-" * len(line))
    for e in entries:
        if "error" in e:
            print(f"{e['profile']:<22}  [WARN] {e['error']}")
            continue
        cells = [e["profile"][:22], (e.get("selected") or "—")[:10]]
        for metric, _, _ in METRICS:
            row = e["best_per_metric"].get(metric)
            if not row:
                cells.append("—")
                continue
            algo = row["best_algo"]
            v = row["best_val"]
            star = "*" if algo == e.get("selected") else ""
            v_str = f"{v:.3f}" if isinstance(v, float) else str(v)
            cells.append(f"{algo}{star}({v_str})")
        print("  ".join(c.ljust(w) for c, w in zip(cells, widths)))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Print per-profile per-metric best algorithm from committed snapshots."
    )
    ap.add_argument("--dir", default=str(DEFAULT_DIR),
                    help="snapshots directory (default: dashboard_live/public/live-data/snapshots)")
    ap.add_argument("--json", action="store_true",
                    help="emit machine-readable JSON instead of the human table")
    args = ap.parse_args()

    root = Path(args.dir)
    entries = collect(root)
    if not entries:
        print(f"[FAIL] no snapshots found under {root}", file=sys.stderr)
        return 1
    usable = [e for e in entries if "best_per_metric" in e and e["best_per_metric"]]
    if not usable:
        print(f"[FAIL] {len(entries)} profile dir(s) found but no usable comparison rows",
              file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"snapshots_dir": str(root), "profiles": entries}, indent=2))
        return 0

    print(f"Snapshot winner analysis: {root}")
    print("(star * after the algorithm marks the LLM-selected algorithm; "
          "value in parens is its absolute score)")
    print()
    print_table(entries)
    print()
    # Per-metric summary across profiles.
    print("By metric, across profiles:")
    for metric, higher, short in METRICS:
        wins: dict[str, list[str]] = {}
        for e in usable:
            row = e.get("best_per_metric", {}).get(metric)
            if not row:
                continue
            wins.setdefault(row["best_algo"], []).append(e["profile"])
        if not wins:
            continue
        direction = "↑" if higher else "↓"
        breakdown = ", ".join(f"{a}({len(p)})" for a, p in sorted(wins.items()))
        print(f"  {short:<8} ({direction} better): {breakdown}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
