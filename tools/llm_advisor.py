"""LLM Scheduling Advisor (Role B).

Pipeline position (see architecture_diagram.md):

    workload_summary.json  -->  llm_advisor.py  -->  recommendation.json
                                      ^
                          feedback_rules.md (fail-only; consumed ONLY when the
                          orchestrator passes --feedback, i.e. opt-in)

Feedback consumption is OPT-IN. The orchestrator passes --feedback only under
its own --use-feedback flag; without it this script gets no feedback path and
advises from the base prompt alone. See docs/orchestrator_design.md.

What it does:
  1. Read `workload_summary.json` (produced by Role A's workload_analyzer.py).
  2. If a --feedback `feedback_rules.md` is passed AND exists, append it to the
     system prompt (opt-in consumption only).
  3. Ask Upstage Solar Pro 3 to recommend ONE of:
         FCFS, RR, PRIORITY, MLFQ, SJF, SRTF
     and explain why, as strict JSON. SJF/SRTF use prediction-based burst
     estimation; the LLM tunes the exponential-averaging predictor only.
  4. Write the result to `recommendation.json`.

The LLM only advises. It does not control the scheduler — this script just
emits `recommendation.json`; algorithm_guard.py validates it downstream.

Usage:
    python3 tools/llm_advisor.py
    python3 tools/llm_advisor.py --in workload_summary.json \
        --out recommendation.json --feedback feedback_rules.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Import the Solar Pro 3 client living next to this file (tools/).
try:
    from tools.solar_client import SolarClient, SolarError
except ImportError:  # when run as `python3 tools/llm_advisor.py`
    from solar_client import SolarClient, SolarError

# Backward-compatible output normalizers (DISPLAY algo name + canonical metric).
# CANONICAL_ALGOS is the single source of truth — keep this set in sync with
# tools/algorithm_guard.py via the same import.
try:
    from tools.schema_compat import (
        CANONICAL_ALGOS,
        normalize_algorithm_name,
        normalize_target_metric,
    )
except ImportError:  # when run as `python3 tools/llm_advisor.py`
    from schema_compat import (  # type: ignore[no-redef]
        CANONICAL_ALGOS,
        normalize_algorithm_name,
        normalize_target_metric,
    )

ALGORITHMS = list(CANONICAL_ALGOS)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

BASE_SYSTEM_PROMPT = f"""You are the LLM Scheduling Advisor for an xv6-based \
educational scheduler lab.

You are given a workload summary describing a set of processes (arrival time, \
priority, I/O behaviour, and CPU/I/O burst COUNTS — never the future burst \
durations). Recommend exactly ONE CPU scheduling algorithm that best fits this \
workload and the user's target metric.

You may ONLY choose from these algorithms:
  - FCFS     : First-Come First-Served (non-preemptive, simple, convoy effect)
  - RR       : Round Robin (preemptive, good response time, baseline)
  - PRIORITY : Priority Scheduling + aging (low-priority starvation risk)
  - MLFQ     : Multi-Level Feedback Queue (favors interactive, aging possible)
  - SJF      : Shortest Job First, prediction-based (non-preemptive; great
               avg waiting/turnaround; long jobs may starve)
  - SRTF     : Shortest Remaining Time First, prediction-based (preemptive
               variant of SJF; long jobs may starve)

SJF and SRTF do NOT receive real future bursts. They estimate the next CPU \
burst with an exponential-averaging predictor that you tune via params. The \
kernel updates predictions only from already-observed CPU usage.

You must also propose algorithm parameters. Schema per algorithm:
  - FCFS     : params = {{}}     (no parameters)
  - RR       : params = {{ "quantum": <int 1-100> }}                ticks per round
  - PRIORITY : params = {{ "aging_threshold": <int 1-10000> }}      ticks before aging
  - MLFQ     : params = {{
                 "queues": <int 2-5>,
                 "quantum": [<int 1-100>, ...]  (length = queues),
                 "aging_threshold": <int 1-10000>,
                 "boost_interval": <int 10-10000>
               }}
  - SJF/SRTF : params = {{
                 "alpha_percent": <int 0-100>,   smoothing weight for the
                                                 last observed burst
                 "initial": <int >=1>,           initial burst guess
                 "min": <int >=1>,               clamp lower bound
                 "max": <int, >=min, <=100000>   clamp upper bound
               }}

The xv6 backend APPLIES your parameters before the workload runs, so they \
matter: RR quantum (setrrquantum), Priority aging_threshold (setpriorityaging), \
MLFQ queues/quantum/boost_interval (setmlfqparams/setmlfqboost), and the \
SJF/SRTF predictor params + per-process burst priors all reach the real kernel \
via syscalls. Algorithm Guard validates and clamps them first; pick values \
inside the ranges above.

You are an ADVISOR only. You do NOT schedule the next process and you NEVER run \
inside the kernel. Your job is to output a recommendation; another component \
will verify it by actually running the workload in xv6. If the recommendation \
underperforms, a host-side post-evaluation correction loop (NOT kernel hot-path \
LLM control) may re-run xv6 with a corrected algorithm. SJF/SRTF never receive \
real future bursts — only predictions from visible features.

When the recommended algorithm is SJF or SRTF, you may ALSO output a per-process \
burst hint list. Derive each hint by REASONING over the visible features in \
`visible_processes` — arrival_time, priority, io_count (number of I/O bursts) \
and burst_count (number of CPU bursts). There is intentionally NO `label`: you \
must INFER whether a process is short/interactive or long/CPU-bound from the \
feature combination (e.g. several CPU bursts interleaved with I/O suggest a \
short, interactive job; a single CPU burst with no I/O suggests a long batch \
job) and then CALIBRATE the predicted magnitude in ticks. DO NOT use any actual \
burst values — they are not in the prompt and you must not invent them by \
guessing the ground truth. Your hint is a *prediction*, mirroring what a smart \
kernel predictor would estimate from the visible features.

Respond with STRICT JSON only (no markdown, no prose outside JSON), with \
exactly these keys (predicted_bursts is OPTIONAL and only relevant for \
SJF/SRTF):
{{
  "algorithm": "<one of FCFS | RR | PRIORITY | MLFQ | SJF | SRTF>",
  "params": {{ ... algorithm-specific, see schema above ... }},
  "reason": "<concise explanation, 2-4 sentences, referencing the workload>",
  "target_metric": "<one of waiting_time | response_time | turnaround_time | \
throughput | starvation | fairness>",
  "confidence": <number between 0 and 1>,
  "predicted_bursts": [   // OPTIONAL — only if algorithm is SJF or SRTF
    {{
      "pid":              <int>,
      "predicted_burst":  <number>,           // first-burst hint in ticks
      "predicted_bursts": [<number>, ...],     // OPTIONAL multi-burst list
      "confidence":       <number 0..1>,
      "basis":            "<short reason citing visible features>"
    }}
  ]
}}
"""


def read_workload_summary(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(
            f"[llm_advisor] workload summary not found: {path}\n"
            f"  Role A's workload_analyzer.py must produce it first."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[llm_advisor] {path} is not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise SystemExit(
            f"[llm_advisor] expected {path} to be a JSON object, got "
            f"{type(data).__name__}"
        )
    return data


# Facts about how THIS xv6 backend actually implements each algorithm. The
# advisor otherwise reasons from generic textbook behavior and systematically
# mismatches the kernel (e.g. xv6 RR uses quantum=1 and preempts every tick, so
# it minimizes response time — a property the model cannot know from the workload
# alone). These are OS-IMPLEMENTATION facts, not the answer and not future-burst
# leakage. Adding them moved measured-best agreement from 1/5 to 4/5 (3-rep
# majority vote on the discriminating xv6 profiles). We intentionally exclude
# benchmark-limitation hints (e.g. "context-switch cost is not charged",
# "throughput does not discriminate") so the model is not steered toward the
# evaluation — only informed of how the kernel runs.
XV6_EXECUTION_FACTS = """

=== THIS xv6 BACKEND — HOW EACH ALGORITHM IS IMPLEMENTED (reason FROM these OS
facts; they describe this kernel's actual behavior, NOT the answer) ===
- RR uses a time quantum of 1 TICK: it PREEMPTS ON EVERY TICK and rotates through
  all RUNNABLE processes, so every ready process gets the CPU almost immediately
  after it arrives. This makes RR very strong on avg_response_time, and strong on
  avg_turnaround_time when jobs are SHORT. However, when ALL jobs are long/CPU-
  bound, RR's per-tick rotation interleaves them so every completion is delayed,
  which HURTS avg_turnaround_time (MLFQ/SJF run long jobs more contiguously).
- FCFS and cold-start SJF/SRTF are non-preemptive: a long job that starts first
  blocks all later arrivals until it finishes (convoy effect).
- SJF/SRTF use an exponential-averaging predictor that only learns from ALREADY-
  observed CPU time and starts from a fixed initial guess. When each process runs
  a single one-shot CPU burst there is no prior history, so the predictor cannot
  distinguish jobs and SJF/SRTF behave close to FCFS.
- PRIORITY runs strictly by priority with slow aging; a low-priority job waits
  behind every higher-priority arrival.
- MLFQ uses a few queues with a short top-queue quantum; it favors short/
  interactive jobs but does NOT preempt as aggressively as RR's per-tick rotation.
"""


def build_system_prompt(feedback_path: Path | None) -> str:
    prompt = BASE_SYSTEM_PROMPT + XV6_EXECUTION_FACTS
    # Consumption is OPT-IN: only inject feedback when a path was EXPLICITLY
    # supplied (feedback_path is not None). The default advise run consumes
    # nothing, so it stays deterministic and stale rules cannot pollute it.
    if feedback_path is not None and feedback_path.is_file():
        rules = feedback_path.read_text(encoding="utf-8").strip()
        if rules:
            prompt += (
                "\n\n--- ADDITIONAL RULES FROM PAST FAILURES "
                "(feedback_rules.md) ---\n"
                f"{rules}\n"
                "Follow these corrective rules carefully.\n"
            )
            print(f"[llm_advisor] applied feedback rules from {feedback_path}")
    return prompt


# Summary keys that must NOT reach the advisor prompt:
#   - total_cpu_work        : the SUM of every process's true CPU burst — an
#                             absolute ground-truth burst aggregate. Sending it
#                             violates the "no future burst leakage" honesty
#                             contract (CLAUDE.md: "Future CPU bursts must not be
#                             given to the LLM as input.").
#   - expected_best_algorithm / expected_behavior : the workload's EVALUATION
#                             answer key. Handing these to the advisor would make
#                             it echo the expected answer, voiding the SUCCESS/
#                             NEAR/FAIL judgment (best_algorithm is determined by
#                             the real cross-algorithm comparison, not this hint).
# NOTE: workload CLASSIFICATION aggregates (cpu_bound_ratio, interactive_ratio,
# burst_count_distribution, has_starvation_risk) are intentionally KEPT — they
# are coarse characterizations a scheduler designer may legitimately use and do
# not reveal any per-process future burst duration. These keys are stripped only
# from the prompt; workload_summary.json on disk keeps them for the dashboard.
_PROMPT_STRIP_KEYS = (
    "total_cpu_work",
    "expected_best_algorithm",
    "expected_behavior",
    # `description` is free text that often names the burst structure outright
    # (e.g. "a long CPU-bound job arrives first; short jobs queue behind") — a
    # soft answer-key. Stripping it forces both the algorithm recommendation and
    # the burst prediction to reason from the numeric visible features, not from
    # a sentence that gives the game away. `id` can encode the same hint.
    "description",
    "id",
    # `workload_file` is the path of the source JSON ("workloads/xv6_interactive
    # .json") — the file NAME names the workload class outright, the exact same
    # soft answer-key as `id`. The path stays in workload_summary.json on disk
    # (dashboard / provenance); only the prompt hides it.
    "workload_file",
    # `family` is the generated-workload PATTERN tag ("interactive"/"convoy"/...)
    # written by the --random-family live mode (workload_families.build_doc). It
    # names the workload class outright, so it is an answer-tag exactly like
    # `description`/`label` — strip it from the prompt while keeping it on disk
    # (the dashboard/run_server use it to label "local environment, run #N").
    "family",
)

# Per-process keys stripped from each `visible_processes` entry before the
# prompt is built. `label` is an on-the-nose tag ("interactive" / "cpu" /
# "predictably_short"): handing it over lets the advisor pattern-match a single
# word instead of REASONING about burst length. We strip it so per-process
# burst prediction must be inferred from multi-dimensional features
# (arrival_time, priority, io_count, burst_count). The label is kept in
# workload_summary.json on disk (for the dashboard and for the coarse top-level
# cpu_bound_ratio / interactive_ratio aggregates) — only the prompt hides it.
_VISIBLE_PROCESS_STRIP_KEYS = ("label",)


_RETRIEVAL_HEADER = (
    "\n\n--- RETRIEVED PRECEDENTS — past workloads with SIMILAR visible features "
    "and the algorithm that ACTUALLY WON when measured on THIS xv6 backend ---\n"
    "Treat these as empirical evidence, not an answer key. Reason about WHICH "
    "visible features (process count, arrival gaps, priority spread, interactive "
    "ratio, ...) separate the winners, then apply that reasoning to the current "
    "workload. Do NOT blindly copy the nearest one; the current workload may "
    "differ on the feature that flips the outcome.\n"
)


def build_retrieval_block(summary: dict, store_path: Path | None, k: int = 3) -> str:
    """OPT-IN retrieval-augmented learning: inject the k most similar PAST
    measured outcomes from the persistent outcome store into the advise prompt.
    This is the personalization / warm-start layer — as the store accumulates a
    user's recurring workload PATTERNS, recommendations improve (measured: see
    experiments/learning_curve_*). Empty string when no store is supplied or no
    relevant precedent exists, so the default advise run is unchanged.

    Honesty: precedents carry only VISIBLE features of OTHER workloads + their
    measured winner; the query's own outcome is excluded by name (we learn from
    SIMILAR past workloads, never from the current one's answer). No future burst
    durations are ever included.
    """
    if store_path is None or not store_path.is_file():
        return ""
    # outcome_store owns the prompt-safe feature extraction + leave-one-out
    # retrieval (single source of truth for the honesty contract).
    sys.path.insert(0, str(PROJECT_ROOT / "experiments"))
    sys.path.insert(0, str(PROJECT_ROOT / "tools"))
    try:
        import outcome_store as osmod  # noqa: PLC0415
    except ImportError:
        return ""
    records = []
    for line in store_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    records = [r for r in records if r.get("features") and r.get("measured_best")]
    if not records:
        return ""
    qf = osmod.prompt_safe_features(summary)
    neighbors = osmod.retrieve(qf, records, k, exclude_name=summary.get("id"))
    if not neighbors:
        return ""
    print(f"[llm_advisor] retrieval ON: injecting {len(neighbors)} precedent(s) "
          f"from {store_path}")
    return _RETRIEVAL_HEADER + osmod.format_examples_for_prompt(neighbors) + "\n"


def build_user_prompt(summary: dict) -> str:
    # Defensive copy with ground-truth / answer-key fields stripped first.
    safe = {k: v for k, v in summary.items() if k not in _PROMPT_STRIP_KEYS}
    # Deep-strip per-process label so burst hints come from reasoning, not a tag.
    procs = safe.get("visible_processes")
    if isinstance(procs, list):
        safe["visible_processes"] = [
            {k: v for k, v in proc.items()
             if k not in _VISIBLE_PROCESS_STRIP_KEYS}
            for proc in procs
            if isinstance(proc, dict)
        ]
    return (
        "Here is the workload summary (JSON):\n\n"
        f"{json.dumps(safe, indent=2, ensure_ascii=False)}\n\n"
        "Recommend the single best scheduling algorithm for this workload "
        "and return the strict JSON object described in the system prompt."
    )


# Range used to clamp LLM-predicted burst values. Matches the xv6 predictor's
# default [min=1, max=100] (proc.c: struct predictor_params). The guard /
# kernel may further clamp; this is the first line of defence.
PREDICTED_BURST_MIN = 1
PREDICTED_BURST_MAX = 100


def _clamp_burst(x: float) -> int:
    """Coerce a numeric burst hint into an int within [MIN, MAX]."""
    v = int(round(float(x)))
    if v < PREDICTED_BURST_MIN: v = PREDICTED_BURST_MIN
    if v > PREDICTED_BURST_MAX: v = PREDICTED_BURST_MAX
    return v


def _validate_predicted_bursts(items, expected_pids: set | None = None) -> list:
    """Validation of the OPTIONAL predicted_bursts[] list.

    Honesty contract (docs/system_limitations.md, no-future-burst rule):
      - Drops malformed entries instead of failing, so a partial model answer
        still yields a usable recommendation.
      - Deduplicates by pid (last hint wins — LLMs sometimes restate).
      - Clamps numeric burst hints to [PREDICTED_BURST_MIN, PREDICTED_BURST_MAX]
        so out-of-range / negative / huge values cannot reach the simulator
        or the xv6 predictor.
      - Drops items whose pid is not in the workload's visible pids when
        `expected_pids` is provided.
    """
    if not isinstance(items, list):
        return []
    by_pid: dict[int, dict] = {}  # pid -> last-seen clean entry (dedup)
    for it in items:
        if not isinstance(it, dict):
            continue
        pid = it.get("pid")
        if not isinstance(pid, int):
            continue
        if expected_pids is not None and pid not in expected_pids:
            continue
        out: dict = {"pid": pid}
        # predicted_burst (scalar)
        pb = it.get("predicted_burst")
        if isinstance(pb, (int, float)):
            out["predicted_burst"] = _clamp_burst(pb)
        # predicted_bursts (list) — also clamp every element
        pb_list = it.get("predicted_bursts")
        if isinstance(pb_list, list):
            pb_clean = [_clamp_burst(x) for x in pb_list
                        if isinstance(x, (int, float))]
            if pb_clean:
                out["predicted_bursts"] = pb_clean
        if "predicted_burst" not in out and "predicted_bursts" not in out:
            continue
        if isinstance(it.get("confidence"), (int, float)):
            c = float(it["confidence"])
            if c < 0.0: c = 0.0
            if c > 1.0: c = 1.0
            out["confidence"] = round(c, 3)
        if isinstance(it.get("basis"), str):
            out["basis"] = it["basis"][:200]
        by_pid[pid] = out  # dedup: later occurrence wins
    return list(by_pid.values())


def validate(rec: dict, summary: dict | None = None) -> dict:
    if not isinstance(rec, dict):
        raise SolarError(f"Model returned non-object JSON: {rec!r}")
    algo = str(rec.get("algorithm", "")).strip()
    # Normalize common casing variants (e.g. "rr", "fcfs").
    match = next((a for a in ALGORITHMS if a.lower() == algo.lower()), None)
    if match is None:
        raise SolarError(
            f"Model recommended an unsupported algorithm: {algo!r}. "
            f"Must be one of {ALGORITHMS}."
        )
    rec["algorithm"] = match
    if not str(rec.get("reason", "")).strip():
        raise SolarError("Model did not provide a 'reason'.")
    rec.setdefault("target_metric", "unspecified")
    rec.setdefault("confidence", None)
    # params is optional here — algorithm_guard.py will fill in defaults
    # and validate ranges. We just check the type.
    params = rec.get("params")
    if params is not None and not isinstance(params, dict):
        raise SolarError(f"'params' must be an object, got {type(params).__name__}.")
    rec.setdefault("params", {})

    # OPTIONAL predicted_bursts[] — only relevant for SJF/SRTF.
    expected_pids = None
    if summary and isinstance(summary.get("visible_processes"), list):
        expected_pids = {vp.get("pid") for vp in summary["visible_processes"]
                         if isinstance(vp.get("pid"), int)}
    rec["predicted_bursts"] = _validate_predicted_bursts(
        rec.get("predicted_bursts"), expected_pids
    )
    # If the LLM picked SJF/SRTF but gave no hints, that's fine — the simulator
    # falls back to EMA. We log it for visibility.
    if match in ("SJF", "SRTF") and not rec["predicted_bursts"]:
        print("[llm_advisor] note: SJF/SRTF without predicted_bursts -> EMA fallback.")
    return rec


# ---------------------------------------------------------------------------
# Feedback mode (Prompt Feedback Loop)
# ---------------------------------------------------------------------------
#
# Pipeline position (architecture_diagram.md, AFTER RUNNING phase):
#
#     outputs/metrics.json  -->  llm_advisor.py --mode feedback
#       (+ recommendation.json, optional)        |
#                                                v
#                                  outputs/feedback_rules.md
#
# Trigger: metrics.py writes a `judgment` field ∈ {SUCCESS, NEAR-SUCCESS, FAIL}.
# Only `FAIL` (regret_score > 0.25, OR starvation_occurred = true) triggers a
# rules update — SUCCESS / NEAR-SUCCESS leave the rules file untouched.
# See docs/evaluation_plan.md for the full judgment criteria.

FEEDBACK_SYSTEM_PROMPT = """You are the Feedback Rule Generator for an \
LLM-based CPU scheduling advisor.

You receive one or more failed evaluations: the advisor recommended an \
algorithm whose measured performance fell into the FAIL bucket \
(regret_score > 0.25, OR starvation occurred). Your job is to write \
prompt-engineering rules that prevent the same mistakes in future \
recommendations.

When EXISTING RULES are shown, you must:
  - NOT repeat or paraphrase any existing rule
  - Only emit rules that capture a pattern the existing rules miss
  - If existing rules already cover every failure pattern shown, emit an
    empty bullet list (just the line "- none")

Each NEW rule MUST contain three parts:
  1. a workload OR metric CONDITION (e.g. "if the target metric is
     avg_response_time and the workload mixes short interactive tasks with
     long CPU-bound tasks")
  2. a scheduling DIRECTIVE — recommend or avoid an algorithm/parameter
     ("prefer MLFQ over FCFS", "avoid SJF when ...")
  3. the metric REASON ("because FCFS causes convoy-driven response delays")

Hard constraints — DO NOT violate these:
  - Do NOT write rules tied to a specific pid, trace tick, run id, or one-off
    process identity (no "P1 waited too long", no "at tick 47").
  - Do NOT write rules that merely describe what happened in the previous run;
    write GENERAL workload-condition -> algorithm/parameter guidance instead.
  - Do NOT emit absolute rules like "always avoid FCFS" UNLESS the triggering
    condition is stated explicitly.
  - Cite the metric and the algorithm by name; avoid restating textbook
    algorithm definitions.
  - Generalize across the failures shown when multiple runs are summarized
    (prefer one or two broad rules over many narrow ones).

Bad (never produce these):
  - Use MLFQ next time.
  - P1 waited too long, so use MLFQ.
  - Always avoid FCFS.

Good:
  - If the target metric is avg_response_time and the workload mixes short \
interactive tasks with long CPU-bound tasks, prefer MLFQ over FCFS because \
FCFS lets a long job at the head create convoy-driven response delays.

When EXISTING RULES already cover a failure pattern, do not restate it.

Write the output as a flat Markdown bullet list. No preamble, no closing \
remarks, no code fences.
"""

FAIL_VERDICTS = {"fail", "failed"}
MAX_RULES = 20  # FIFO cap; oldest rules drop first when over the limit
MIN_RULE_LEN = 12  # bullets shorter than this are treated as noise

# Marker for the bullet section so we can replace just the rules and keep
# the file's header comment block.
RULES_SECTION_MARKER = "<!-- RULES_BEGIN -->"
RULES_SECTION_END = "<!-- RULES_END -->"


def load_metrics(metrics_path: Path) -> dict:
    if not metrics_path.is_file():
        raise SystemExit(
            f"[feedback] metrics.json not found: {metrics_path}\n"
            f"  Role A's metrics.py must produce it first."
        )
    try:
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[feedback] {metrics_path} is not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise SystemExit(
            f"[feedback] expected metrics.json to be a JSON object, got "
            f"{type(data).__name__}"
        )
    return data


def load_recommendation_context(rec_path: Path) -> dict | None:
    """Optional: pull algorithm/target_metric from recommendation.json so the
    feedback prompt has more context. Missing/invalid file is non-fatal."""
    if not rec_path.is_file():
        return None
    try:
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return rec if isinstance(rec, dict) else None


def resolve_metrics_paths(spec: str) -> list[Path]:
    """Resolve a --metrics argument into a sorted list of file paths.

    Accepts: a single file, a directory (scans for *.json), or a glob pattern.
    """
    p = Path(spec)
    if p.is_file():
        return [p]
    if p.is_dir():
        return sorted(p.glob("*.json"))
    # Fallback: treat as glob relative to cwd.
    import glob as _glob
    matches = sorted(Path(m) for m in _glob.glob(spec) if Path(m).is_file())
    return matches


def parse_rules_from_markdown(text: str) -> list[str]:
    """Extract bullet items from a markdown body. Returns trimmed rule texts
    (without the leading bullet marker). Filters out empties and the literal
    sentinel "none"."""
    rules: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.lstrip()
        for marker in ("- ", "* "):
            if stripped.startswith(marker):
                rule = stripped[len(marker):].strip()
                if rule and rule.lower() not in {"none", "n/a", "(none)"}:
                    if len(rule) >= MIN_RULE_LEN:
                        rules.append(rule)
                break
    return rules


def load_existing_rules(rules_path: Path) -> list[str]:
    """Read prior rules from a feedback_rules.md file. Returns [] if absent."""
    if not rules_path.is_file():
        return []
    return parse_rules_from_markdown(rules_path.read_text(encoding="utf-8"))


def _dedupe_keep_order(rules: list[str]) -> list[str]:
    """Case-insensitive de-dupe while preserving insertion order."""
    seen: set[str] = set()
    out: list[str] = []
    for r in rules:
        key = r.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def fail_summary_block(metrics: dict, rec: dict | None, source: str) -> str:
    """One indented block describing a single FAILed run."""
    algo = metrics.get("scheduling_algorithm", "?")
    best_algo = metrics.get("best_algorithm")
    target_metric = (rec or {}).get("target_metric", "?")
    lines = [
        f"FAILED RUN ({source}):",
        f"  - recommended algorithm : {algo}",
        f"  - best algorithm        : "
        f"{best_algo or 'unknown (no cross-algorithm comparison)'}",
        f"  - target metric         : {target_metric}",
        f"  - judgment              : {metrics.get('judgment', '?')}",
        f"  - regret_score          : {metrics.get('regret_score', '?')}",
        f"  - starvation_occurred   : {metrics.get('starvation_occurred', '?')}",
        f"  - avg_response_time     : {metrics.get('avg_response_time', '?')}",
        f"  - avg_waiting_time      : {metrics.get('avg_waiting_time', '?')}",
        f"  - avg_turnaround_time   : {metrics.get('avg_turnaround_time', '?')}",
        f"  - throughput            : {metrics.get('throughput', '?')}",
        f"  - max_waiting_time      : {metrics.get('max_waiting_time', '?')}",
        f"  - preemption_count      : {metrics.get('preemption_count', '?')}",
    ]
    if rec and rec.get("reason"):
        lines.append(f"  - advisor reasoning     : {rec['reason']}")
    if rec and rec.get("params"):
        lines.append(f"  - advisor params        : {json.dumps(rec['params'])}")
    return "\n".join(lines)


def build_feedback_user_prompt(
    fail_blocks: list[str], existing_rules: list[str]
) -> str:
    """Build the user prompt: existing rules first (to dedupe against), then
    every failed-run summary, then the directive."""
    parts: list[str] = []
    if existing_rules:
        parts.append("EXISTING RULES (do NOT repeat or paraphrase):")
        parts.extend(f"- {r}" for r in existing_rules)
        parts.append("")
    parts.append(
        f"FAILED EVALUATIONS TO LEARN FROM "
        f"({len(fail_blocks)} run{'s' if len(fail_blocks) != 1 else ''}):"
    )
    parts.append("")
    parts.extend(fail_blocks)
    parts.append("")
    if len(fail_blocks) > 1:
        parts.append(
            "Generalize across all the runs above. Prefer one or two broad "
            "rules over many narrow ones."
        )
    else:
        parts.append(
            "Focus on what conditions in the workload should have steered the "
            "advisor away from this algorithm."
        )
    parts.append(
        "Write only the new rule bullets (one per line, starting with '- '). "
        "If existing rules already cover this pattern, output just '- none'."
    )
    return "\n".join(parts)


def render_rules_file(
    rules: list[str], sources: list[Path], n_added: int
) -> str:
    """Render the full feedback_rules.md content."""
    timestamp = datetime.now(timezone.utc).isoformat()
    src_names = ", ".join(s.name for s in sources) or "(none)"
    header = (
        f"<!-- Generated by tools/llm_advisor.py (feedback mode)\n"
        f"     last_updated : {timestamp}\n"
        f"     total_rules  : {len(rules)} (added {n_added} this run, "
        f"capped at {MAX_RULES})\n"
        f"     last_sources : {src_names} -->\n\n"
        f"{RULES_SECTION_MARKER}\n"
    )
    body = "\n".join(f"- {r}" for r in rules) if rules else "(no rules yet)"
    return header + body + f"\n{RULES_SECTION_END}\n"


def run_feedback(metrics_spec: str, rules_out: Path, rec_path: Path) -> int:
    metrics_paths = resolve_metrics_paths(metrics_spec)
    if not metrics_paths:
        raise SystemExit(
            f"[feedback] no metrics files match {metrics_spec!r}. Pass a file, "
            f"directory, or glob (e.g. 'outputs/runs/*.json')."
        )

    # Collect every FAIL metrics file with its parsed payload.
    fail_runs: list[tuple[Path, dict]] = []
    skipped: list[tuple[Path, str]] = []
    for mp in metrics_paths:
        m = load_metrics(mp)
        verdict = str(m.get("judgment", "")).strip().lower()
        if verdict in FAIL_VERDICTS:
            fail_runs.append((mp, m))
        else:
            skipped.append((mp, m.get("judgment", "?")))

    if skipped:
        for p, v in skipped:
            print(f"[feedback] skip {p.name}: judgment={v!r} (not FAIL)")

    if not fail_runs:
        print(
            f"[feedback] no FAIL judgments across {len(metrics_paths)} file(s); "
            f"rules unchanged."
        )
        return 0

    rec = load_recommendation_context(rec_path)
    if rec is None:
        print(f"[feedback] note: {rec_path} unavailable; running without it.")

    existing_rules = load_existing_rules(rules_out)
    if existing_rules:
        print(
            f"[feedback] {len(existing_rules)} existing rule(s) loaded — "
            f"asking LLM for non-duplicate additions only."
        )

    fail_blocks = [fail_summary_block(m, rec, p.name) for p, m in fail_runs]
    user_prompt = build_feedback_user_prompt(fail_blocks, existing_rules)

    print(
        f"[feedback] {len(fail_runs)} FAIL run(s); querying Solar Pro 3..."
    )
    try:
        client = SolarClient()
        rules_md = client.complete(
            prompt=user_prompt,
            system=FEEDBACK_SYSTEM_PROMPT,
            temperature=0.2,
        )
    except SolarError as exc:
        raise SystemExit(f"[feedback] LLM error: {exc}")

    new_rules = parse_rules_from_markdown(rules_md)
    # Drop anything the LLM accidentally repeated from the existing set.
    existing_keys = {r.casefold() for r in existing_rules}
    fresh = [r for r in new_rules if r.casefold() not in existing_keys]

    if not new_rules:
        print(
            "[feedback] LLM returned no usable rules "
            "(empty or below length floor); rules file untouched."
        )
        return 0
    if not fresh:
        print(
            "[feedback] LLM produced only duplicates of existing rules; "
            "rules file untouched."
        )
        return 0

    combined = _dedupe_keep_order(existing_rules + fresh)
    if len(combined) > MAX_RULES:
        dropped = len(combined) - MAX_RULES
        combined = combined[-MAX_RULES:]  # FIFO — keep most recent MAX_RULES
        print(f"[feedback] capped at {MAX_RULES}; dropped {dropped} oldest rule(s).")

    rules_out.parent.mkdir(parents=True, exist_ok=True)
    rules_out.write_text(
        render_rules_file(combined, [p for p, _ in fail_runs], n_added=len(fresh)),
        encoding="utf-8",
    )
    print(f"[feedback] wrote {len(combined)} rule(s) → {rules_out}")
    for r in fresh:
        print(f"  + {r}")
    return 0


# ---------------------------------------------------------------------------
# Advise mode (default — the original behavior)
# ---------------------------------------------------------------------------


def run_advise(in_path: Path, out_path: Path, feedback_path: Path | None,
               retrieval_store: Path | None = None) -> int:
    summary = read_workload_summary(in_path)
    system_prompt = build_system_prompt(feedback_path)
    # OPT-IN retrieval-augmented learning (personalization warm-start). Appended
    # AFTER the feedback block; both default to OFF so the demo stays deterministic.
    system_prompt += build_retrieval_block(summary, retrieval_store)
    user_prompt = build_user_prompt(summary)

    try:
        client = SolarClient()  # reads UPSTAGE_API_KEY from .env
        print(f"[llm_advisor] querying Solar Pro 3 (model={client.model})...")
        rec = client.complete_json(
            prompt=user_prompt,
            system=system_prompt,
            temperature=0.0,
        )
        rec = validate(rec, summary=summary)
    except SolarError as exc:
        raise SystemExit(f"[llm_advisor] LLM error: {exc}")

    # Dashboard data-contract compatibility: emit the canonical keys ALONGSIDE
    # the legacy ones the rest of the pipeline already validates/consumes.
    #   - recommended_scheduling_algorithm : DISPLAY form (e.g. "Priority")
    #   - target_metric                    : canonical (e.g. "avg_response_time")
    # The legacy `algorithm` key is preserved untouched for backward compat.
    rec["recommended_scheduling_algorithm"] = normalize_algorithm_name(
        rec.get("algorithm")
    )
    if rec.get("target_metric") and rec.get("target_metric") != "unspecified":
        rec["target_metric"] = normalize_target_metric(rec.get("target_metric"))

    rec["_meta"] = {
        "source": "tools/llm_advisor.py",
        "model": client.model,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workload_summary": str(in_path),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"[llm_advisor] recommended {rec['algorithm']} "
        f"(target={rec.get('target_metric')}) -> {out_path}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM Scheduling Advisor (Role B)")
    parser.add_argument(
        "--mode",
        choices=["advise", "feedback"],
        default="advise",
        help="advise: recommend an algorithm; feedback: write rules from FAIL judgment",
    )
    parser.add_argument(
        "--in",
        dest="in_path",
        default=str(PROJECT_ROOT / "outputs" / "workload_summary.json"),
        help="[advise] path to workload_summary.json",
    )
    parser.add_argument(
        "--out",
        dest="out_path",
        default=str(PROJECT_ROOT / "outputs" / "recommendation.json"),
        help="[advise] path to write recommendation.json",
    )
    parser.add_argument(
        "--feedback",
        dest="feedback_path",
        default=None,
        help="path to feedback_rules.md. advise: OPT-IN input — feedback is "
        "consumed ONLY when this flag is explicitly passed (default: no "
        "consumption). feedback: output path (defaults to "
        "outputs/feedback_rules.md when omitted).",
    )
    parser.add_argument(
        "--retrieval-store",
        dest="retrieval_store",
        default=None,
        help="[advise] path to a persistent outcome-store JSONL "
        "(features->measured_best per past run). OPT-IN: when supplied, the k "
        "most similar past outcomes are injected into the advise prompt "
        "(retrieval-augmented learning). Default: no retrieval.",
    )
    parser.add_argument(
        "--metrics",
        dest="metrics_path",
        default=str(PROJECT_ROOT / "outputs" / "metrics.json"),
        help="[feedback] metrics.json source — accepts a single file, a "
        "directory (scans *.json), or a glob like 'outputs/runs/*.json' "
        "to learn from multiple FAIL runs at once",
    )
    parser.add_argument(
        "--rec",
        dest="rec_context_path",
        default=str(PROJECT_ROOT / "outputs" / "recommendation.json"),
        help="[feedback] recommendation.json used for added context (optional)",
    )
    args = parser.parse_args()

    if args.mode == "feedback":
        # feedback GENERATION: --feedback is the OUTPUT path; default when omitted.
        fb_out = Path(args.feedback_path) if args.feedback_path else (
            PROJECT_ROOT / "outputs" / "feedback_rules.md"
        )
        return run_feedback(
            args.metrics_path,  # string: file, dir, or glob — resolved inside
            fb_out,
            Path(args.rec_context_path),
        )
    # advise: consumption is OPT-IN — only when --feedback explicitly supplied.
    fb_in = Path(args.feedback_path) if args.feedback_path else None
    ret_store = Path(args.retrieval_store) if args.retrieval_store else None
    return run_advise(Path(args.in_path), Path(args.out_path), fb_in, ret_store)


if __name__ == "__main__":
    sys.exit(main())
