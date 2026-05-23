"""
Trace Parser — converts raw xv6 console output into structured trace JSONL.

xv6 sched_debug() emits lines like:
    SCHED [tick=42] pid=3 event=PREEMPT state=RUNNABLE reason=quantum_expired

Run:
    python3 tools/trace_parser.py --input xv6_console.log \\
                                  --algo RR \\
                                  --out outputs/trace_rr.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# Regex for xv6 sched_debug output
_LINE_RE = re.compile(
    r"SCHED\s+\[tick=(?P<tick>\d+)\]\s+"
    r"pid=(?P<pid>-?\d+)\s+"
    r"event=(?P<event>\w+)"
    r"(?:\s+state=(?P<state>\w+))?"
    r"(?:\s+queue=(?P<queue>\d+))?"
    r"(?:\s+priority=(?P<priority>\d+))?"
    r"(?:\s+reason=(?P<reason>\w+))?"
    r"(?:\s+turnaround=(?P<turnaround>\d+))?"
    r"(?:\s+waiting=(?P<waiting>\d+))?"
    r"(?:\s+response=(?P<response>\d+))?"
)


def parse_line(line: str, algo: str) -> dict | None:
    m = _LINE_RE.search(line)
    if not m:
        return None
    ev: dict = {
        "tick":  int(m.group("tick")),
        "algo":  algo,
        "event": m.group("event"),
        "pid":   int(m.group("pid")),
    }
    for field in ("state", "queue", "priority", "reason"):
        v = m.group(field)
        if v is not None:
            ev[field] = int(v) if field in ("queue", "priority") else v
    for field in ("turnaround", "waiting", "response"):
        v = m.group(field)
        if v is not None:
            ev[field] = int(v)
    return ev


def parse_file(path: Path, algo: str) -> list[dict]:
    events = []
    with open(path) as f:
        for line in f:
            ev = parse_line(line, algo)
            if ev:
                events.append(ev)
    return sorted(events, key=lambda e: e["tick"])


def save_jsonl(events: list[dict], out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Parse xv6 console log → trace JSONL")
    ap.add_argument("--input", required=True, help="xv6 console log file")
    ap.add_argument("--algo",  required=True, help="Scheduling algorithm name (RR, MLFQ, ...)")
    ap.add_argument("--out",   default="outputs/trace.jsonl", help="Output JSONL path")
    args = ap.parse_args()

    in_path  = Path(args.input)
    out_path = Path(args.out)

    if not in_path.exists():
        print(f"ERROR: input not found: {in_path}", file=sys.stderr)
        return 1

    events = parse_file(in_path, args.algo)
    save_jsonl(events, out_path)
    print(f"Parsed {len(events)} events → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
