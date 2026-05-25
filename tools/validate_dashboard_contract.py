"""Dashboard data-contract validator.

Lightweight, non-blocking checker for dashboard_live/public/live-data/ against
docs/dashboard_data_contract.md. It WARNS on schema mismatches but only fails
(exit 1) on a hard error such as a missing directory or unreadable JSON.

Run:
    python3 tools/validate_dashboard_contract.py
    python3 tools/validate_dashboard_contract.py --dir dashboard_live/public/live-data
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = PROJECT_ROOT / "dashboard_live" / "public" / "live-data"

TRACE_FILES = [
    "trace_rr.jsonl", "trace_fcfs.jsonl", "trace_priority.jsonl",
    "trace_mlfq.jsonl", "trace_sjf.jsonl", "trace_srtf.jsonl",
]
MANIFEST_FIELDS = [
    "mode", "version", "updated_at", "workload", "algorithms",
    "recommended_algorithm", "target_metric",
]


class Report:
    def __init__(self) -> None:
        self.ok = 0
        self.warn = 0

    def good(self, msg: str) -> None:
        self.ok += 1
        print(f"  [OK]   {msg}")

    def warn_(self, msg: str) -> None:
        self.warn += 1
        print(f"  [WARN] {msg}")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def check_recommendation(d: Path, r: Report) -> None:
    p = d / "recommendation.json"
    if not p.is_file():
        r.warn_("recommendation.json missing")
        return
    rec = _load(p)
    if rec.get("recommended_scheduling_algorithm") or rec.get("algorithm"):
        r.good("recommendation.json has an algorithm key")
    else:
        r.warn_("recommendation.json lacks recommended_scheduling_algorithm/algorithm")


def check_guard(d: Path, r: Report) -> None:
    p = d / "guard_decision.json"
    if not p.is_file():
        r.warn_("guard_decision.json missing")
        return
    g = _load(p)
    if g.get("scheduling_algorithm") or g.get("algorithm"):
        r.good("guard_decision.json has an algorithm key")
    else:
        r.warn_("guard_decision.json lacks scheduling_algorithm/algorithm")
    if str(g.get("guard_result", "")):
        r.good(f"guard_result = {g.get('guard_result')}")


def check_manifest(d: Path, r: Report) -> None:
    p = d / "manifest.json"
    if not p.is_file():
        r.warn_("manifest.json missing")
        return
    m = _load(p)
    missing = [f for f in MANIFEST_FIELDS if f not in m]
    if missing:
        r.warn_(f"manifest.json missing fields: {missing}")
    else:
        r.good("manifest.json has all required fields")
    if str(m.get("mode")) not in ("simulator", "xv6-log", "fallback"):
        r.warn_(f"manifest.mode unexpected: {m.get('mode')!r}")


def check_metrics(d: Path, r: Report) -> None:
    p = d / "metrics.json"
    if not p.is_file():
        r.warn_("metrics.json missing")
        return
    m = _load(p)
    cmp = m.get("comparison")
    if isinstance(cmp, dict) and cmp:
        r.good(f"metrics.json comparison present ({len(cmp)} algos)")
    else:
        r.warn_("metrics.json has no non-empty comparison")


def check_traces(d: Path, r: Report) -> None:
    required = {"tick", "algo", "event", "pid"}
    for fname in TRACE_FILES:
        p = d / fname
        if not p.is_file():
            r.warn_(f"{fname} missing")
            continue
        n = 0
        bad = 0
        sched_seen = 0
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:  # noqa: BLE001
                bad += 1
                continue
            n += 1
            # kernel/sched events should carry the required fields
            if ev.get("event") in {"DISPATCH", "PREEMPT", "EXIT", "QUEUE_CHANGE",
                                    "ARRIVE", "SLEEP", "WAKEUP"}:
                sched_seen += 1
                if not required.issubset(ev.keys()):
                    bad += 1
        if bad:
            r.warn_(f"{fname}: {n} events, {bad} malformed/missing required fields")
        else:
            r.good(f"{fname}: {n} events ({sched_seen} sched)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate dashboard live-data contract")
    ap.add_argument("--dir", default=str(DEFAULT_DIR),
                    help="live-data directory to validate")
    args = ap.parse_args()

    d = Path(args.dir)
    print(f"Validating dashboard data contract: {d}")
    if not d.is_dir():
        print(f"[ERROR] directory not found: {d}", file=sys.stderr)
        return 1

    r = Report()
    try:
        check_manifest(d, r)
        check_recommendation(d, r)
        check_guard(d, r)
        check_metrics(d, r)
        check_traces(d, r)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] unreadable JSON: {exc}", file=sys.stderr)
        return 1

    print(f"\nSummary: {r.ok} OK, {r.warn} WARN")
    if r.warn:
        print("Contract warnings present (non-blocking).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
