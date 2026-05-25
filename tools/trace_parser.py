"""
Trace Parser — converts raw xv6 console output into structured trace JSONL.

The xv6 kernel (xv6-riscv/kernel/proc.c) emits scheduling lines like:
    [SCHED] tick=12 algo=MLFQ event=DISPATCH pid=3 priority=2 queue=0
    [SCHED] tick=2 algo=MLFQ event=PREEMPT pid=1 state=RUNNABLE queue=1 \
            priority=1 reason=quantum_expired
Events include: DISPATCH, PREEMPT, EXIT, QUEUE_CHANGE, ARRIVE, SLEEP, WAKEUP.
Lines may also carry from_queue/to_queue, turnaround, waiting, response.

A future user program (schedtest.c) emits metadata lines like:
    [SCHEDTEST] event=RUN_BEGIN algo=MLFQ seed=42 profile=interactive
    [SCHEDTEST] event=PROC_DEF pid=3 arrival=0 cpu_burst=5 priority=2 label=interactive
    [SCHEDTEST] event=CHILD_START pid=3 priority=2
    [SCHEDTEST] event=CHILD_EXIT pid=3
    [SCHEDTEST] event=RUN_END algo=MLFQ seed=42 profile=interactive

Only lines containing [SCHED] or [SCHEDTEST] are processed; everything else
(boot spam, shell prompts) is ignored. Each prefix is followed by generic
key=value tokens parsed without positional assumptions.

Run:
    python3 tools/trace_parser.py --input xv6_console.log \\
                                  --algo RR \\
                                  --out outputs/trace.jsonl

    # convenience: write trace_<algo>.jsonl into a directory
    python3 tools/trace_parser.py --input xv6_console.log \\
                                  --algo MLFQ \\
                                  --out-dir outputs

    # optionally stamp every event with run metadata
    python3 tools/trace_parser.py --input xv6_console.log --algo SJF \\
                                  --out outputs/trace.jsonl \\
                                  --seed 42 --profile interactive
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# Prefixes we recognize, mapped to the "kind" field stamped on each event.
_PREFIXES = {
    "[SCHED]": "sched",
    "[SCHEDTEST]": "schedtest",
}

# Tokens that should be coerced to int when their value looks numeric.
_INT_FIELDS = {
    "tick", "pid", "queue", "priority",
    "from_queue", "to_queue",
    "turnaround", "waiting", "response",
    "arrival", "cpu_burst", "seed",
}

# Canonical algorithm names (UPPERCASE).
_ALGO_CANON = {
    "rr": "RR",
    "fcfs": "FCFS",
    "priority": "PRIORITY",
    "mlfq": "MLFQ",
    "sjf": "SJF",
    "srtf": "SRTF",
}


def canon_algo(algo: str | None) -> str | None:
    """Normalize an algorithm name to its canonical UPPERCASE form."""
    if algo is None:
        return None
    return _ALGO_CANON.get(algo.strip().lower(), algo.strip().upper())


def _looks_int(value: str) -> bool:
    """True if value is a (possibly negative) base-10 integer literal."""
    if value.startswith("-"):
        value = value[1:]
    return value.isdigit() and value != ""


def _coerce(key: str, value: str):
    """Coerce a token value: ints where it makes sense, else string."""
    if _looks_int(value):
        # Always coerce pure integer literals to int.
        return int(value)
    return value


def parse_line(line: str, algo: str | None = None) -> dict | None:
    """Parse a single console line into a normalized event dict.

    Returns None if the line is not a [SCHED]/[SCHEDTEST] line (ignored
    silently) or raises no exception — malformed recognized lines are
    detected by the caller via a missing 'event' key.
    """
    prefix = None
    kind = None
    idx = -1
    for pfx, knd in _PREFIXES.items():
        i = line.find(pfx)
        if i != -1:
            prefix = pfx
            kind = knd
            idx = i
            break

    if prefix is None:
        return None  # not a line we care about; ignore silently

    # Everything after the prefix is a sequence of key=value tokens.
    tail = line[idx + len(prefix):]

    tokens: dict = {}
    for tok in tail.split():
        if "=" not in tok:
            continue
        key, _, value = tok.partition("=")
        if not key:
            continue
        tokens[key] = _coerce(key, value) if key in _INT_FIELDS else (
            int(value) if _looks_int(value) else value
        )

    ev: dict = {
        "tick": tokens.get("tick", None),
        "algo": canon_algo(tokens.get("algo")) or canon_algo(algo),
        "event": tokens.get("event"),
        "source": "xv6",
        "kind": kind,
    }

    # Carry every remaining token through (already coerced).
    for key, value in tokens.items():
        if key in ("tick", "algo", "event"):
            continue
        ev[key] = value

    return ev


def parse_file(
    path: Path,
    algo: str | None = None,
    seed: int | None = None,
    profile: str | None = None,
) -> tuple[list[dict], int]:
    """Parse a console log file.

    Returns (events, parse_errors). A recognized [SCHED]/[SCHEDTEST] line
    without a parseable event= token counts as a parse error and is skipped.
    """
    events: list[dict] = []
    parse_errors = 0

    with open(path) as f:
        for line in f:
            try:
                ev = parse_line(line, algo)
            except Exception:
                # A recognized line that blew up still counts as an error,
                # but only if it carried a known prefix.
                if any(p in line for p in _PREFIXES):
                    parse_errors += 1
                continue

            if ev is None:
                continue  # not a [SCHED]/[SCHEDTEST] line

            if not ev.get("event"):
                # Recognized prefix but no usable event= token.
                parse_errors += 1
                continue

            if seed is not None:
                ev["seed"] = seed
            if profile is not None:
                ev["profile"] = profile

            events.append(ev)

    # Stable sort by tick; null-tick (schedtest metadata) treated as -1 so
    # RUN_BEGIN and friends keep their original relative order up front.
    events.sort(key=lambda e: e["tick"] if e.get("tick") is not None else -1)
    return events, parse_errors


def save_jsonl(events: list[dict], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Parse xv6 console log → trace JSONL")
    ap.add_argument("--input", required=True, help="raw xv6 console log file")
    ap.add_argument("--algo", required=True,
                    help="Scheduling algorithm name (RR, FCFS, PRIORITY, MLFQ, SJF, SRTF)")
    ap.add_argument("--out", default="outputs/trace.jsonl", help="Output JSONL path")
    ap.add_argument("--out-dir", default=None,
                    help="If set, write trace_<algo>.jsonl into this dir instead of --out")
    ap.add_argument("--seed", type=int, default=None,
                    help="Optional run seed; stamped on every event")
    ap.add_argument("--profile", default=None,
                    help="Optional workload profile; stamped on every event")
    args = ap.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"ERROR: input not found: {in_path}", file=sys.stderr)
        return 1

    if args.out_dir:
        algo_lower = args.algo.strip().lower()
        out_path = Path(args.out_dir) / f"trace_{algo_lower}.jsonl"
    else:
        out_path = Path(args.out)

    events, parse_errors = parse_file(
        in_path, args.algo, seed=args.seed, profile=args.profile
    )
    save_jsonl(events, out_path)
    print(f"Parsed {len(events)} events ({parse_errors} parse errors) -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
