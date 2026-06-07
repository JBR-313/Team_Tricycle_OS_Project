#!/usr/bin/env python3
"""xv6_determinism_probe.py — is the real-xv6 metric pipeline DETERMINISTIC under
heavy preemption? This gates the adaptive (mid-run switch) measurement: if even a
static run does not reproduce across reruns, an adaptive A/B on real xv6 is not
trustworthy (the earlier burst --hints arm was non-deterministic).

Runs the same (profile, algo) N times via the orchestrator's exact QEMU + parse
+ metrics path and reports whether avg_turnaround/waiting/response reproduce.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

import orchestrator as orch  # noqa: E402
from metrics import compute_metrics  # noqa: E402

RAW = PROJECT_ROOT / "outputs" / "adaptive" / "xv6_probe"
KEYS = ("avg_turnaround_time", "avg_waiting_time", "avg_response_time")
# (profile, algo, reps) — preemption-heavy cases most likely to be flaky.
CASES = [("convoy_tail", "rr", 3), ("preempt_stream", "srtf", 3),
         ("convoy_tail", "fcfs", 3)]


def _run(profile, algo, rep):
    RAW.mkdir(parents=True, exist_ok=True)
    raw = RAW / f"{profile}_{algo}_r{rep}.log"
    trace = f"trace_{profile}_{algo}_r{rep}.jsonl"
    if not orch.qemu_run_schedtest(algo, 42, profile, raw, False, None):
        return None
    orch.parse_xv6_log(raw, algo.upper(), 42, profile, RAW, False, trace)
    tp = RAW / trace
    return compute_metrics(orch._load_jsonl(tp)) if tp.is_file() else None


def main():
    if not orch.ensure_xv6_built(False):
        print("xv6 build failed"); return 1
    all_ok = True
    for profile, algo, reps in CASES:
        print(f"\n=== {profile} / {algo}  x{reps} ===")
        vals = {k: [] for k in KEYS}
        for r in range(reps):
            m = _run(profile, algo, r)
            if not m:
                print(f"  rep {r}: NO RUN_END"); all_ok = False; continue
            for k in KEYS:
                vals[k].append(m.get(k))
            print(f"  rep {r}: " + "  ".join(f"{k.split('_')[1]}={m.get(k)}" for k in KEYS))
        for k in KEYS:
            uniq = set(v for v in vals[k] if v is not None)
            status = "DETERMINISTIC" if len(uniq) == 1 else "NON-DETERMINISTIC"
            if len(uniq) != 1:
                all_ok = False
            print(f"    {k:22} -> {status}  values={sorted(uniq)}")
    print(f"\n[probe] overall: {'ALL DETERMINISTIC' if all_ok else 'SOME NON-DETERMINISTIC'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
