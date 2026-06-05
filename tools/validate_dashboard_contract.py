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
        elif n == 0:
            # Empty trace would silently render an empty Gantt at the demo.
            # Treat as a contract violation, not just an empty file.
            r.warn_(f"{fname}: empty — backend produced no parsable events")
        else:
            r.good(f"{fname}: {n} events ({sched_seen} sched, {exits} EXIT)")
        if exits == 0 and n > 0:
            r.warn_(f"{fname}: zero EXIT events — metrics cannot be computed")


def _has_correction_applied(obj) -> bool:
    """True iff any nested key in obj equals 'CORRECTION_APPLIED'.

    The preview surface promises this trace event never appears here —
    it is reserved for the (future) closed-loop apply.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "CORRECTION_APPLIED" or v == "CORRECTION_APPLIED":
                return True
            if _has_correction_applied(v):
                return True
    elif isinstance(obj, list):
        for v in obj:
            if v == "CORRECTION_APPLIED" or _has_correction_applied(v):
                return True
    return False


# Allowed event types and correction types (kept in sync with
# tools/event_detector.py and tools/correction_proposer.py).
_EVENT_TYPES = {"starvation", "high_response_time",
                "high_preemption_rate", "low_throughput"}
_EVENT_SEVERITIES = {"low", "medium", "high"}
_CORRECTION_TYPES = {"aging_strengthen", "quantum_decrease",
                     "quantum_increase", "parameter_update",
                     "algorithm_change", "no_op"}


def _check_runtime_events(d: Path, r: Report) -> tuple[dict | None, list[dict]]:
    """Validate runtime_events.json. Returns (doc, events) or (None, []) if absent."""
    p = d / "runtime_events.json"
    if not p.is_file():
        return None, []
    doc = _load(p)
    if doc.get("applied") is True:
        r.warn_("runtime_events.json carries applied=true (must be observational, not applied)")
    if _has_correction_applied(doc):
        r.warn_("runtime_events.json mentions CORRECTION_APPLIED (reserved for live apply)")
    events = doc.get("events")
    if not isinstance(events, list):
        r.warn_("runtime_events.json: events is not a list")
        return doc, []
    total = doc.get("total_problems")
    if not isinstance(total, int) or total < 0:
        r.warn_("runtime_events.json: total_problems missing or negative")
    elif total != len(events):
        r.warn_(f"runtime_events.json: total_problems={total} != len(events)={len(events)}")
    for i, e in enumerate(events):
        if not isinstance(e, dict):
            r.warn_(f"runtime_events.json: event[{i}] is not an object")
            continue
        if e.get("type") not in _EVENT_TYPES:
            r.warn_(f"runtime_events.json: event[{i}].type={e.get('type')!r} not in {sorted(_EVENT_TYPES)}")
        if e.get("severity") not in _EVENT_SEVERITIES:
            r.warn_(f"runtime_events.json: event[{i}].severity={e.get('severity')!r} not in {sorted(_EVENT_SEVERITIES)}")
        if not isinstance(e.get("tick"), int):
            r.warn_(f"runtime_events.json: event[{i}].tick missing or not int")
        if not isinstance(e.get("pid"), int):
            r.warn_(f"runtime_events.json: event[{i}].pid missing or not int")
    r.good(f"runtime_events.json: {len(events)} event(s)")
    return doc, events


def _check_correction_proposal(d: Path, events: list[dict], r: Report) -> dict | None:
    """Validate correction_proposal.json. Returns the doc or None if absent."""
    p = d / "correction_proposal.json"
    if not p.is_file():
        if events:
            r.warn_("correction_proposal.json missing despite non-empty runtime_events.events")
        return None
    if not events:
        r.warn_("correction_proposal.json present but runtime_events.events is empty (orphan proposal)")
    doc = _load(p)
    # Honesty invariants — always ERROR if violated.
    if doc.get("preview_only") is not True:
        r.hard_error("correction_proposal.json: preview_only is not true")
    if doc.get("applied") is not False:
        r.hard_error("correction_proposal.json: applied is not false")
    if _has_correction_applied(doc):
        r.hard_error("correction_proposal.json: mentions CORRECTION_APPLIED")
    proposed = doc.get("proposed") or {}
    ct = proposed.get("correction_type")
    if ct not in _CORRECTION_TYPES:
        r.warn_(f"correction_proposal.json: correction_type={ct!r} not in {sorted(_CORRECTION_TYPES)}")
    if not isinstance(proposed.get("new_scheduling_algorithm"), str) \
            or not proposed.get("new_scheduling_algorithm"):
        r.warn_("correction_proposal.json: new_scheduling_algorithm missing or empty")
    if not isinstance(proposed.get("new_params"), dict):
        r.warn_("correction_proposal.json: new_params is not an object")
    te = proposed.get("triggering_event") or {}
    if events:
        match = any((isinstance(te, dict)
                     and te.get("tick") == ev.get("tick")
                     and te.get("type") == ev.get("type")) for ev in events)
        if not match:
            r.warn_("correction_proposal.json: triggering_event does not match any runtime_events.events entry")
    r.good(f"correction_proposal.json: {ct} on {proposed.get('new_scheduling_algorithm')}")
    return doc


def _check_correction_guard(d: Path, proposal: dict | None, r: Report) -> dict | None:
    """Validate correction_guard_decision.json. Returns the doc or None if absent."""
    p = d / "correction_guard_decision.json"
    if not p.is_file():
        if proposal is not None:
            r.hard_error("correction_guard_decision.json missing despite correction_proposal.json present")
        return None
    if proposal is None:
        r.warn_("correction_guard_decision.json present but no correction_proposal.json (orphan decision)")
    doc = _load(p)
    if doc.get("preview_only") is not True:
        r.hard_error("correction_guard_decision.json: preview_only is not true")
    if doc.get("applied") is not False:
        r.hard_error("correction_guard_decision.json: applied is not false")
    if _has_correction_applied(doc):
        r.hard_error("correction_guard_decision.json: mentions CORRECTION_APPLIED")
    gr = doc.get("guard_result")
    if gr not in ("accepted", "rejected"):
        r.warn_(f"correction_guard_decision.json: guard_result={gr!r} not in {{accepted, rejected}}")
    if gr == "rejected":
        rps = doc.get("rejected_params")
        if not isinstance(rps, list) or not rps:
            r.warn_("correction_guard_decision.json: rejected without non-empty rejected_params")
        fb = doc.get("fallback") or {}
        if fb.get("correction_type") != "no_op":
            r.warn_("correction_guard_decision.json: rejected without fallback.correction_type=no_op")
    r.good(f"correction_guard_decision.json: {gr}")
    return doc


def _check_preview(d: Path, r: Report) -> None:
    """Optional --preview pass. Validates the three preview artifacts if any
    of them is present, against the §3 schema in
    docs/runtime_correction_preview_validation.md.
    """
    print("\nValidating runtime-correction preview artifacts")
    events_doc, events = _check_runtime_events(d, r)
    proposal = _check_correction_proposal(d, events, r)
    _check_correction_guard(d, proposal, r)
    if events_doc is None and proposal is None:
        # The (d / "correction_guard_decision.json").is_file() branch is
        # handled inside _check_correction_guard via proposal=None ⇒ WARN
        # only when the file actually exists; if it does not exist we
        # reach here and report "preview not present".
        if not (d / "correction_guard_decision.json").is_file():
            r.good("preview not present (no preview files in this directory)")


def check_correction_applied(d: Path, r: Report) -> None:
    """Validate correction_applied.json — the record of the host-side
    post-evaluation correction APPLY loop. Unlike the preview proposal/guard
    files, this artifact MAY carry applied=true (a real second xv6 run was
    executed). Absent file is fine (the loop only writes it on the xv6 backend).
    """
    p = d / "correction_applied.json"
    if not p.is_file():
        return
    doc = _load(p)
    applied = doc.get("applied")
    if not isinstance(applied, bool):
        r.warn_("correction_applied.json: 'applied' missing or not a bool")
        return
    if applied:
        required = ["mode", "original_algorithm", "corrected_algorithm",
                    "target_metric", "trace_file"]
        missing = [k for k in required if not doc.get(k)]
        if missing:
            r.warn_(f"correction_applied.json applied=true missing: {missing}")
        else:
            r.good(f"correction_applied.json: applied {doc.get('original_algorithm')} "
                   f"-> {doc.get('corrected_algorithm')} "
                   f"({doc.get('original_judgment')} -> {doc.get('corrected_judgment')})")
        tf = doc.get("trace_file")
        if tf and not (d / tf).is_file():
            r.warn_(f"correction_applied.json references missing trace_file {tf!r}")
    else:
        if not doc.get("reason"):
            r.warn_("correction_applied.json applied=false lacks a 'reason'")
        else:
            r.good("correction_applied.json: applied=false (no correction warranted)")


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

def _check_dir(d: Path, r: Report) -> None:
    """Run every per-directory check against `d` and report into `r`."""
    manifest = check_manifest(d, r)
    rec = check_recommendation(d, r)
    guard = check_guard(d, r)
    check_metrics(d, r)
    check_traces(d, r)
    check_correction_applied(d, r)
    cross_check(manifest, rec, guard, r)


def _check_snapshots(snapshots_dir: Path, r: Report) -> None:
    """Validate every <profile>/ sub-directory under snapshots_dir.

    Reads the optional `snapshots_manifest.json` next to it (one level
    above) only for cross-reference; missing manifest is non-fatal.
    """
    if not snapshots_dir.is_dir():
        r.warn_(f"snapshots directory not found: {snapshots_dir}")
        return
    profiles = sorted(p for p in snapshots_dir.iterdir() if p.is_dir())
    if not profiles:
        r.warn_(f"snapshots directory is empty: {snapshots_dir}")
        return
    # Optional manifest cross-link: parent of snapshots_dir holds it.
    sm_path = snapshots_dir.parent / "snapshots_manifest.json"
    listed: set[str] = set()
    if sm_path.is_file():
        sm = _load(sm_path)
        listed = {entry.get("profile") for entry in sm.get("profiles", [])
                  if isinstance(entry, dict)}
        r.good(f"snapshots_manifest.json found ({len(listed)} profile(s) listed)")
    else:
        r.warn_(f"snapshots_manifest.json not found at {sm_path}")

    for prof_dir in profiles:
        prof = prof_dir.name
        print(f"\n--- snapshot: {prof} ---")
        _check_dir(prof_dir, r)
        if listed and prof not in listed:
            r.warn_(f"snapshot dir {prof}/ exists but not in snapshots_manifest.json")
    for prof in listed - {p.name for p in profiles}:
        r.warn_(f"snapshots_manifest.json lists {prof!r} but no dir exists")


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate dashboard live-data contract")
    ap.add_argument("--dir", default=str(DEFAULT_DIR),
                    help="live-data directory to validate")
    ap.add_argument("--strict", action="store_true",
                    help="treat WARN as ERROR and exit non-zero")
    ap.add_argument("--snapshots", default=None,
                    help="if set, also validate each <profile>/ sub-directory "
                         "under this path (typically dashboard_live/public/live-data/snapshots)")
    ap.add_argument("--preview", action="store_true",
                    help="opt-in: also validate runtime correction preview artifacts "
                         "(runtime_events.json + correction_proposal.json + "
                         "correction_guard_decision.json). Default mode never requires them. "
                         "See docs/runtime_correction_preview_validation.md.")
    args = ap.parse_args()

    d = Path(args.dir)
    print(f"Validating dashboard data contract: {d}")
    if not d.is_dir():
        print(f"[ERROR] directory not found: {d}", file=sys.stderr)
        return 1

    r = Report(strict=args.strict)
    try:
        _check_dir(d, r)
        if args.snapshots:
            print(f"\nValidating snapshots: {args.snapshots}")
            _check_snapshots(Path(args.snapshots), r)
        if args.preview:
            _check_preview(d, r)
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
