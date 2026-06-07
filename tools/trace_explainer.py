"""Trace Explainer (Role B).

Pipeline position (architecture_diagram.md, AFTER RUNNING phase):

    trace.jsonl  +  metrics.json  -->  trace_explainer.py  -->  trace_explanation.json
                         ^                    ^
              recommendation.json (optional)  correction_proposal.json (optional)

What it does:
  1. Read a scheduling trace (`trace.jsonl`) and the computed `metrics.json`.
  2. Summarize both into a compact, token-friendly digest.
  3. If `correction_proposal.json` exists, surface the runtime monitor's
     would-have-proposed correction so the explanation can reference it as
     evidence ("the runtime monitor flagged X and suggested Y").
  4. Ask Upstage Solar Pro 3 to explain — in natural language — what happened
     and why, returning the strict JSON schema the dashboard consumes
     (docs/dashboard_data_contract.md §7).
  5. Write the result to `trace_explanation.json`.

The LLM only explains an already-finished run; it does not control anything.
The correction proposal (if present) was preview-only, so the explanation
must phrase it as "would have suggested" — never as "applied".

Usage:
    python3 tools/trace_explainer.py
    python3 tools/trace_explainer.py --trace outputs/trace_mlfq.jsonl \
        --metrics outputs/metrics.json --out outputs/trace_explanation.json
    python3 tools/trace_explainer.py --proposal outputs/correction_proposal.json ...
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

try:
    from tools.solar_client import SolarClient, SolarError
except ImportError:  # when run as `python3 tools/trace_explainer.py`
    from solar_client import SolarClient, SolarError

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SYSTEM_PROMPT = """You are the Trace Explainer for an xv6-based scheduler lab.

You are given (1) a digest of a scheduling trace and (2) the computed metrics \
for one finished run. Explain, in clear natural language, what the scheduler \
did and WHY the metrics turned out as they did. Identify the dominant \
scheduling pattern (e.g. convoy_effect, short_job_priority, starvation, \
fair_timeslicing, priority_inversion).

You are explaining an already-finished run — do not propose to change the \
scheduler, only describe and, in `suggestion`, note what algorithm/parameters \
would likely do better.

If a RUNTIME MONITOR PREVIEW PROPOSAL block appears in the user prompt, \
treat it as additional evidence: the runtime monitor (preview-only, never \
applied to xv6) flagged events during the run and would have suggested a \
correction. Mention it briefly in `evidence` using language like "the \
runtime monitor would have suggested …" — never claim the correction was \
applied.

Respond with STRICT JSON only (no markdown, no prose outside JSON), exactly \
these keys:
{
  "scheduling_algorithm": "<algorithm that ran>",
  "detected_pattern": "<one snake_case label for the dominant pattern>",
  "summary": "<2-3 sentence plain-language summary of the run>",
  "main_reason": "<the single biggest driver of the observed metrics>",
  "evidence": ["<concrete fact from the trace/metrics>", "..."],
  "suggestion": "<which algorithm/params would likely do better, and why>",
  "runtime_corrections_applied": <integer>
}
"""


def load_json(path: Path, *, required: bool) -> dict | None:
    if not path.is_file():
        if required:
            raise SystemExit(f"[trace_explainer] required file not found: {path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        if required:
            raise SystemExit(f"[trace_explainer] {path} is not valid JSON: {exc}")
        return None


def load_trace(path: Path) -> list[dict]:
    if not path.is_file():
        raise SystemExit(
            f"[trace_explainer] trace not found: {path}\n"
            f"  Role C's scheduler/simulator must produce it first."
        )
    events = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError:
            continue  # skip malformed lines, keep going
    if not events:
        raise SystemExit(f"[trace_explainer] no usable events in {path}")
    return events


def summarize_trace(events: list[dict]) -> dict:
    """Compress a trace into a small digest the LLM can read cheaply.

    Trace events use the keys ``algo`` and ``tick`` (NOT ``algorithm``/``time``)
    in BOTH backends.  The two backends differ in how arrival is recorded:
      - simulator emits an ``ARRIVE`` event carrying the arrival ``tick``;
      - xv6 emits a ``PROC_DEF`` event whose ``tick`` is null and whose arrival
        lives in a dedicated ``arrival`` field.
    A process is only "real" if it was defined via ARRIVE or PROC_DEF; this also
    filters the xv6 schedtest harness pid, which only ever appears in DISPATCH.
    """
    counts = Counter(e.get("event") for e in events)
    algos = {e.get("algo") for e in events if e.get("algo")}

    # Per-process timeline: arrival, first dispatch (response), exit.
    procs: dict = {}
    defined: set = set()
    for e in events:
        pid = e.get("pid")
        if pid is None:
            continue
        p = procs.setdefault(
            pid, {"arrive": None, "first_run": None, "exit": None}
        )
        ev, t = e.get("event"), e.get("tick")
        if ev == "ARRIVE":
            defined.add(pid)
            if p["arrive"] is None:
                p["arrive"] = t
        elif ev == "PROC_DEF":
            defined.add(pid)
            if p["arrive"] is None:
                p["arrive"] = e.get("arrival")
        elif ev == "DISPATCH" and p["first_run"] is None:
            p["first_run"] = t
        elif ev == "EXIT":
            p["exit"] = t

    timeline = []
    for pid in sorted(p for p in procs if p in defined):
        p = procs[pid]
        resp = (
            p["first_run"] - p["arrive"]
            if p["first_run"] is not None and p["arrive"] is not None
            else None
        )
        timeline.append(
            {"pid": pid, "arrive": p["arrive"], "first_run": p["first_run"],
             "exit": p["exit"], "response": resp}
        )

    return {
        "algorithm": next(iter(algos)) if len(algos) == 1 else sorted(algos),
        "total_events": len(events),
        "event_counts": dict(counts),
        "preemptions": counts.get("PREEMPT", 0),
        "corrections_applied": counts.get("CORRECTION_APPLIED", 0),
        "process_timeline": timeline,
    }


def _proposal_digest(proposal: dict) -> dict | None:
    """Extract the minimum the LLM needs to mention the preview correction.

    Returns None if the proposal is not a usable preview record.
    """
    if not isinstance(proposal, dict):
        return None
    if proposal.get("preview_only") is not True or proposal.get("applied") is not False:
        return None
    proposed = proposal.get("proposed") or {}
    if not isinstance(proposed, dict):
        return None
    triggering = proposed.get("triggering_event") or {}
    return {
        "preview_only": True,
        "applied": False,
        "current_algorithm": proposal.get("current_scheduling_algorithm"),
        "would_propose": {
            "correction_type": proposed.get("correction_type"),
            "new_algorithm": proposed.get("new_scheduling_algorithm"),
            "rationale": proposed.get("rationale"),
        },
        "triggering_event_type": triggering.get("type"),
        "triggering_event_detail": triggering.get("detail"),
        "mode": (proposal.get("_meta") or {}).get("mode"),
    }


def build_user_prompt(
    digest: dict,
    metrics: dict | None,
    rec: dict | None,
    proposal_digest: dict | None,
) -> str:
    parts = ["TRACE DIGEST:", json.dumps(digest, indent=2, ensure_ascii=False)]
    if metrics:
        # Drop the bulky per-process array; the digest already has a timeline.
        slim = {k: v for k, v in metrics.items() if k != "per_process"}
        parts += ["\nMETRICS:", json.dumps(slim, indent=2, ensure_ascii=False)]
    if rec and rec.get("target_metric"):
        parts.append(f"\nTARGET METRIC: {rec['target_metric']}")
    if proposal_digest:
        parts += [
            "\nRUNTIME MONITOR — PREVIEW PROPOSAL (NOT applied to xv6; "
            "phrase as 'would have suggested', never as 'was applied'):",
            json.dumps(proposal_digest, indent=2, ensure_ascii=False),
        ]
    parts.append(
        "\nExplain this run and return the strict JSON object described in the "
        "system prompt."
    )
    return "\n".join(parts)


def validate(exp: dict, digest: dict) -> dict:
    if not isinstance(exp, dict):
        raise SolarError(f"Model returned non-object JSON: {exp!r}")
    exp.setdefault("scheduling_algorithm", digest.get("algorithm"))
    for key in ("detected_pattern", "summary", "main_reason", "suggestion"):
        exp.setdefault(key, "")
    if not isinstance(exp.get("evidence"), list):
        exp["evidence"] = [str(exp.get("evidence", ""))] if exp.get("evidence") else []
    # Trust the trace for the correction count, not the model.
    exp["runtime_corrections_applied"] = digest.get("corrections_applied", 0)
    return exp


def main() -> int:
    parser = argparse.ArgumentParser(description="Trace Explainer (Role B)")
    parser.add_argument(
        "--trace",
        dest="trace_path",
        default=str(PROJECT_ROOT / "outputs" / "trace.jsonl"),
        help="path to the scheduling trace (.jsonl)",
    )
    parser.add_argument(
        "--metrics",
        dest="metrics_path",
        default=str(PROJECT_ROOT / "outputs" / "metrics.json"),
        help="path to metrics.json (optional but recommended)",
    )
    parser.add_argument(
        "--rec",
        dest="rec_path",
        default=str(PROJECT_ROOT / "outputs" / "recommendation.json"),
        help="recommendation.json for the target metric (optional)",
    )
    parser.add_argument(
        "--proposal",
        dest="proposal_path",
        default=str(PROJECT_ROOT / "outputs" / "correction_proposal.json"),
        help="correction_proposal.json from the runtime monitor (optional). "
        "When present and preview_only=true, the explanation will reference "
        "what the monitor would have proposed.",
    )
    parser.add_argument(
        "--out",
        dest="out_path",
        default=str(PROJECT_ROOT / "outputs" / "trace_explanation.json"),
        help="path to write trace_explanation.json",
    )
    args = parser.parse_args()

    events = load_trace(Path(args.trace_path))
    digest = summarize_trace(events)
    metrics = load_json(Path(args.metrics_path), required=False)
    rec = load_json(Path(args.rec_path), required=False)
    proposal_raw = load_json(Path(args.proposal_path), required=False)
    proposal_digest = _proposal_digest(proposal_raw) if proposal_raw else None
    if proposal_digest:
        print(
            f"[trace_explainer] including runtime monitor preview "
            f"({proposal_digest['would_propose'].get('correction_type')} → "
            f"{proposal_digest['would_propose'].get('new_algorithm')})"
        )

    try:
        client = SolarClient()
        print(f"[trace_explainer] querying Solar Pro 3 (model={client.model})...")
        exp = client.complete_json(
            prompt=build_user_prompt(digest, metrics, rec, proposal_digest),
            system=SYSTEM_PROMPT,
            temperature=0.2,
        )
        exp = validate(exp, digest)
    except SolarError as exc:
        raise SystemExit(f"[trace_explainer] LLM error: {exc}")

    exp["_meta"] = {
        "source": "tools/trace_explainer.py",
        "model": client.model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trace": str(Path(args.trace_path)),
    }

    out_path = Path(args.out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(exp, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"[trace_explainer] {exp.get('detected_pattern')} "
        f"(algo={exp.get('scheduling_algorithm')}) -> {out_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
