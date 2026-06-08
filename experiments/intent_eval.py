#!/usr/bin/env python3
"""intent_eval.py — does the LLM correctly translate a NATURAL-LANGUAGE workload
intent into a SENSIBLE, guard-valid scheduling config? (docs/GOAL_semantic.md)

This is the LLM's uncontested lane: there is NO numeric heuristic that reads an
operator's English. We grade a translation against a standard OS rubric — the LLM
sees ONLY the intent, never the rubric. We report intent->acceptable-family match
rate and Algorithm-Guard pass rate. Honest framing: this is NOT "the LLM picks the
metric-optimal algorithm" (measured negative on xv6, info-bounded); it is "the LLM
maps human intent to a valid, sensible configuration", which has no classical
substitute.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from intent_advisor import recommend_from_intent          # noqa: E402
from algorithm_guard import validate_schema, normalize_algorithm, normalize_metric  # noqa: E402

OUT_DIR = ROOT / "outputs" / "intent_eval"
CACHE = OUT_DIR / "intent_cache.json"

# OS-textbook rubric: intent -> the set of DEFENSIBLE algorithm choices. The LLM
# never sees this. Multiple algorithms are accepted where standard reasoning
# allows more than one.
CASES = [
    {"intent": "Interactive desktop session. Users type commands and expect the "
               "system to feel instant. Responsiveness above all else.",
     "accept": {"RR", "MLFQ"}},
    {"intent": "Overnight batch analytics: a handful of long, CPU-bound jobs run "
               "unattended. Maximize total throughput; nobody is waiting at a "
               "terminal, latency does not matter.",
     "accept": {"FCFS", "SJF"}},
    {"intent": "A mix of many short interactive tasks and a couple of long "
               "background jobs. Keep the short tasks snappy, but the long jobs "
               "must still make progress and never starve.",
     "accept": {"MLFQ"}},
    {"intent": "Jobs have strict importance levels set by an admin. Important jobs "
               "should run ahead of others, but even the least important job must "
               "eventually run — no permanent starvation.",
     "accept": {"PRIORITY", "MLFQ"}},
    {"intent": "We can estimate how long each job will run. Run the shortest jobs "
               "first to minimize the average waiting time. Jobs run to completion "
               "once started.",
     "accept": {"SJF"}},
    {"intent": "Short jobs keep arriving over time and should be able to interrupt "
               "a longer job that is currently running, so average waiting time "
               "stays as low as possible.",
     "accept": {"SRTF"}},
    {"intent": "A web server handling many small, latency-sensitive requests. Tail "
               "latency and fairness across requests matter most.",
     "accept": {"RR", "MLFQ"}},
    {"intent": "All jobs are roughly equal length and arrive together. We just want "
               "simple, predictable, low-overhead first-come-first-served behavior.",
     "accept": {"FCFS", "RR"}},
]


def _key(intent: str) -> str:
    return hashlib.sha1(intent.encode()).hexdigest()[:16]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="re-elicit from the LLM even if cached")
    args = ap.parse_args()

    cache = json.loads(CACHE.read_text()) if CACHE.is_file() else {}
    client = None
    rows = []
    for c in CASES:
        k = _key(c["intent"])
        if k in cache and not args.refresh:
            rec = cache[k]
        else:
            if client is None:
                from solar_client import SolarClient
                client = SolarClient()
                print(f"[intent] eliciting via {client.model}")
            rec = recommend_from_intent(c["intent"], client)
            cache[k] = rec
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(cache, indent=2) + "\n")

        ok_schema, err = validate_schema(rec)
        algo = normalize_algorithm(rec.get("algorithm", "")) if ok_schema else None
        metric_ok = normalize_metric(rec.get("target_metric") or "") is not None
        guard_valid = bool(ok_schema and algo and metric_ok)
        family_match = algo in c["accept"] if algo else False
        rows.append({
            "intent": c["intent"][:60] + "…",
            "accept": sorted(c["accept"]),
            "picked": algo or rec.get("algorithm"),
            "target_metric": rec.get("target_metric"),
            "guard_valid": guard_valid,
            "schema_err": err,
            "family_match": family_match,
        })

    n = len(rows)
    fam = sum(r["family_match"] for r in rows)
    gv = sum(r["guard_valid"] for r in rows)
    report = {"n": n, "family_match_rate": round(fam / n, 3),
              "guard_pass_rate": round(gv / n, 3), "rows": rows}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "intent_eval.json").write_text(json.dumps(report, indent=2) + "\n")

    print("\n=== Intent → scheduling config (LLM sees only the English) ===")
    for r in rows:
        mark = "OK " if r["family_match"] else "XX "
        g = "guard✓" if r["guard_valid"] else "guard✗"
        print(f"  {mark} picked={str(r['picked']):8} accept={r['accept']}  "
              f"{g}  metric={r['target_metric']}")
    print(f"\n  intent→family match: {fam}/{n} ({report['family_match_rate']*100:.0f}%)")
    print(f"  guard-valid config : {gv}/{n} ({report['guard_pass_rate']*100:.0f}%)")
    print(f"\n[intent] wrote {OUT_DIR / 'intent_eval.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
