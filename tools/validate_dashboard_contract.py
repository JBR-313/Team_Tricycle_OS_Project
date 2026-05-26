"""Dashboard data-contract validator.

Lightweight checker for `dashboard_live/public/live-data/` against
`docs/dashboard_data_contract.md`. By default it WARNS on schema
mismatches and only fails (exit 1) on a hard error (missing directory,
unreadable JSON). With `--strict`, warnings escalate to errors so the
orchestrator (or CI) can refuse to publish broken live-data.

Run:
    python3 tools/validate_dashboard_contract.py
    python3 tools/validate_dashboard_contract.py --dir dashboard_live/public/live-data
    python3 tools/validate_dashboard_contract.py --strict
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

# Manifest fields the dashboard still reads (legacy schema mirrors).
LEGACY_MANIFEST_FIELDS = [
    "mode", "version", "updated_at", "workload", "algorithms",
    "recommended_algorithm", "target_metric",
]
# Manifest fields the orchestrator added for honesty (new schema).
NEW_MANIFEST_FIELDS = [
    "backend", "seed", "workload_type",
    "llm_selected_algorithm", "algorithms_executed",
    "generated_at", "orchestrator_version",
]
ALLOWED_BACKENDS = {"xv6", "simulator", "fallback"}
ALLOWED_MODES = {"simulator", "xv6-log", "xv6", "fallback"}

# Trace events that must carry these fields.
SCHED_EVENTS = {"DISPATCH", "PREEMPT", "EXIT", "QUEUE_CHANGE",
                "ARRIVE", "SLEEP", "WAKEUP"}
REQUIRED_TRACE_FIELDS = {"tick", "algo", "event", "pid"}

REQUIRED_COMPARISON_KEYS = {
    "avg_waiting_time", "avg_response_time", "avg_turnaround_time",
    "throughput", "max_waiting_time", "preemption_count",
    "starvation_occurred", "judgment",
}


class Report:
    """Collects OK/WARN/ERROR lines. Strict mode escalates WARN -> ERROR."""

    def __init__(self, strict: bool = False) -> None:
        self.ok = 0
        self.warn = 0
        self.error = 0
        self.strict = strict

    def good(self, msg: str) -> None:
        self.ok += 1
        print(f"  [OK]    {msg}")

    def warn_(self, msg: str) -> None:
        if self.strict:
            self.error += 1
            print(f"  [ERROR] {msg}")
        else:
            self.warn += 1
            print(f"  [WARN]  {msg}")

    def hard_error(self, msg: str) -> None:
        self.error += 1
        print(f"  [ERROR] {msg}")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ── individual checks ─────────────────────────────────────────────────────────

def check_manifest(d: Path, r: Report) -> dict:
    p = d / "manifest.json"
    if not p.is_file():
        r.warn_("manifest.json missing")
        return {}
    m = _load(p)

    missing_legacy = [f for f in LEGACY_MANIFEST_FIELDS if f not in m]
    if missing_legacy:
        r.warn_(f"manifest.json missing legacy fields: {missing_legacy}")
    else:
        r.good("manifest.json has all legacy fields")

    missing_new = [f for f in NEW_MANIFEST_FIELDS if f not in m]
    if missing_new:
        r.warn_(f"manifest.json missing new (honesty) fields: {missing_new}")
    else:
        r.good("manifest.json has all new (honesty) fields")

    backend = str(m.get("backend", ""))
    if backend and backend not in ALLOWED_BACKENDS:
        r.warn_(f"manifest.backend unexpected: {backend!r}")
    mode = str(m.get("mode", ""))
    if mode and mode not in ALLOWED_MODES:
        r.warn_(f"manifest.mode unexpected: {mode!r}")

    seed = m.get("seed")
    if seed is not None and not isinstance(seed, int):
        r.warn_(f"manifest.seed should be int, got {type(seed).__name__}")

    execd = m.get("algorithms_executed") or m.get("algorithms")
    if not isinstance(execd, list) or not execd:
        r.warn_("manifest has no algorithms_executed / algorithms list")
    return m


def check_recommendation(d: Path, r: Report) -> dict:
    p = d / "recommendation.json"
    if not p.is_file():
        r.warn_("recommendation.json missing")
        return {}
    rec = _load(p)
    if rec.get("recommended_scheduling_algorithm") or rec.get("algorithm"):
        r.good("recommendation.json has an algorithm key")
    else:
        r.warn_("recommendation.json lacks recommended_scheduling_algorithm/algorithm")
    return rec


def check_guard(d: Path, r: Report) -> dict:
    p = d / "guard_decision.json"
    if not p.is_file():
        r.warn_("guard_decision.json missing")
        return {}
    g = _load(p)
    if g.get("scheduling_algorithm") or g.get("algorithm"):
        r.good("guard_decision.json has an algorithm key")
    else:
        r.warn_("guard_decision.json lacks scheduling_algorithm/algorithm")
    gr = str(g.get("guard_result", ""))
    if gr:
        r.good(f"guard_result = {gr}")
    else:
        r.warn_("guard_decision.json lacks guard_result")
    return g


def check_metrics(d: Path, r: Report) -> dict:
    p = d / "metrics.json"
    if not p.is_file():
        r.warn_("metrics.json missing")
        return {}
    m = _load(p)
    cmp = m.get("comparison")
    if not isinstance(cmp, dict) or not cmp:
        r.warn_("metrics.json has no non-empty comparison")
        return m
    r.good(f"metrics.json comparison present ({len(cmp)} algos)")
    for algo, row in cmp.items():
        if not isinstance(row, dict):
            r.warn_(f"comparison[{algo}] is not an object")
            continue
        missing = REQUIRED_COMPARISON_KEYS - set(row.keys())
        if missing:
            r.warn_(f"comparison[{algo}] missing keys: {sorted(missing)}")
    if not m.get("scheduling_algorithm"):
        r.warn_("metrics.json lacks top-level scheduling_algorithm")
    if "judgment" not in m:
        r.warn_("metrics.json lacks top-level judgment")
    return m


def check_traces(d: Path, r: Report) -> None:
    for fname in TRACE_FILES:
        p = d / fname
        if not p.is_file():
            r.warn_(f"{fname} missing")
            continue
        n = 0
        bad = 0
        sched_seen = 0
        exits = 0
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            n += 1
            evt = ev.get("event")
            if evt in SCHED_EVENTS:
                sched_seen += 1
                if not REQUIRED_TRACE_FIELDS.issubset(ev.keys()):
                    bad += 1
            if evt == "EXIT":
                exits += 1
        if bad:
            r.warn_(f"{fname}: {n} events, {bad} malformed/missing fields")
        else:
            r.good(f"{fname}: {n} events ({sched_seen} sched, {exits} EXIT)")
        if exits == 0 and n > 0:
            r.warn_(f"{fname}: zero EXIT events — metrics cannot be computed")


def cross_check(manifest: dict, rec: dict, guard: dict, r: Report) -> None:
    """Surface any disagreement between manifest, recommendation, and guard."""
    if not (manifest and rec and guard):
        return
    rec_algo = rec.get("recommended_scheduling_algorithm") or rec.get("algorithm")
    guard_algo = guard.get("scheduling_algorithm") or guard.get("algorithm")
    manifest_algo = (manifest.get("llm_selected_algorithm")
                     or manifest.get("recommended_algorithm"))

    def norm(x):
        return str(x).strip().lower() if x else ""

    a, b, c = norm(rec_algo), norm(guard_algo), norm(manifest_algo)
    if a and b and c and (a == b == c):
        r.good(f"recommendation/guard/manifest agree on algorithm: {manifest_algo}")
    else:
        r.warn_(
            f"algorithm disagreement: recommendation={rec_algo!r} "
            f"guard={guard_algo!r} manifest={manifest_algo!r}"
        )


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Validate dashboard live-data contract")
    ap.add_argument("--dir", default=str(DEFAULT_DIR),
                    help="live-data directory to validate")
    ap.add_argument("--strict", action="store_true",
                    help="treat WARN as ERROR and exit non-zero")
    args = ap.parse_args()

    d = Path(args.dir)
    print(f"Validating dashboard data contract: {d}")
    if not d.is_dir():
        print(f"[ERROR] directory not found: {d}", file=sys.stderr)
        return 1

    r = Report(strict=args.strict)
    try:
        manifest = check_manifest(d, r)
        rec = check_recommendation(d, r)
        guard = check_guard(d, r)
        check_metrics(d, r)
        check_traces(d, r)
        cross_check(manifest, rec, guard, r)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] unreadable JSON: {exc}", file=sys.stderr)
        return 1

    print(f"\nSummary: {r.ok} OK, {r.warn} WARN, {r.error} ERROR")
    if r.error:
        return 1
    if r.warn:
        print("Contract warnings present (non-blocking).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
