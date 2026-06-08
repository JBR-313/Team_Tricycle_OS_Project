"""Algorithm Guard (Role B).

Validates LLM recommendations before passing to scheduler.

Pipeline position:
    recommendation.json (from llm_advisor)
        ↓
    algorithm_guard.py (this module)
        ↓
    guard_decision.json (to the xv6 backend)

The guard ensures:
  1. JSON schema is valid
  2. Algorithm is supported
  3. Metric is supported
  4. Algorithm-metric pair makes OS sense
  5. Parameters are in valid ranges
  6. Confidence is acceptable

This protects the system from unsound LLM recommendations.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Backward-compatible output normalizers (DISPLAY algo name + canonical metric).
# CANONICAL_ALGOS is the single source of truth for the supported algorithm set
# — keep this in lockstep with tools/llm_advisor.py via the same import.
try:
    from tools.schema_compat import (
        CANONICAL_ALGOS,
        normalize_algorithm_name,
        normalize_target_metric,
    )
except ImportError:  # when run as `python3 tools/algorithm_guard.py`
    from schema_compat import (  # type: ignore[no-redef]
        CANONICAL_ALGOS,
        normalize_algorithm_name,
        normalize_target_metric,
    )

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# RR/FCFS/PRIORITY/MLFQ implemented in xv6; SJF/SRTF are prediction-based
# (exponential averaging) — see docs/system_limitations.md.
SUPPORTED_ALGORITHMS = list(CANONICAL_ALGOS)
SUPPORTED_METRICS = [
    "response_time",
    "turnaround_time",
    "waiting_time",
    "throughput",
    "starvation",
    "fairness",
]

# Alias mappings (normalize input metric names)
METRIC_ALIASES = {
    "avg_response_time": "response_time",
    "avg_turnaround_time": "turnaround_time",
    "avg_waiting_time": "waiting_time",
    "avg_starvation": "starvation",
    "response": "response_time",
    "turnaround": "turnaround_time",
    "waiting": "waiting_time",
    "fair": "fairness",
}

# Algorithm-Metric Compatibility Matrix (0.0 to 1.0)
# Higher = better fit for this metric; lower = risky or ineffective.
COMPATIBILITY_MATRIX = {
    "FCFS": {
        "response_time": 0.2,  # convoy effect → poor response
        "turnaround_time": 0.5,
        "waiting_time": 0.3,  # convoy effect
        "throughput": 0.8,
        "starvation": 0.9,
        "fairness": 0.4,  # arrival-order; convoy hurts fairness
    },
    "RR": {
        "response_time": 0.9,  # excellent
        "turnaround_time": 0.7,
        "waiting_time": 0.7,
        "throughput": 0.8,
        "starvation": 0.95,
        "fairness": 0.95,  # time-slicing is the fairness baseline
    },
    "PRIORITY": {
        "response_time": 0.7,
        "turnaround_time": 0.6,
        "waiting_time": 0.7,
        "throughput": 0.6,
        "starvation": 0.2,  # ⚠️ HIGH RISK: low-priority starvation
        "fairness": 0.2,  # priority discrimination
    },
    "MLFQ": {
        "response_time": 0.95,  # excellent
        "turnaround_time": 0.8,
        "waiting_time": 0.9,
        "throughput": 0.85,
        "starvation": 0.95,  # with aging
        "fairness": 0.7,  # aging helps, but queue tiers differ
    },
    "SJF": {
        "response_time": 0.8,
        "turnaround_time": 0.95,  # minimizes avg turnaround
        "waiting_time": 0.95,  # optimal avg waiting (non-preemptive)
        "throughput": 0.8,
        "starvation": 0.5,  # long jobs may starve
        "fairness": 0.3,  # favors short jobs; long jobs disadvantaged
    },
    "SRTF": {
        "response_time": 0.95,  # preemptive shortest-remaining
        "turnaround_time": 0.95,
        "waiting_time": 0.95,
        "throughput": 0.85,
        "starvation": 0.5,  # long jobs may starve
        "fairness": 0.3,  # favors short jobs
    },
}

# Reject if score is below this; warn if below WARN threshold.
COMPAT_REJECT_THRESHOLD = 0.4
COMPAT_WARN_THRESHOLD = 0.6
# Confidence is INFORMATIONAL ONLY and never rejects (we validate input format,
# not the model's self-reported confidence). Kept solely to emit a soft warning.
CONFIDENCE_WARN_THRESHOLD = 0.5

# Per-algorithm parameter ranges (min, max) and safe defaults.
# Out-of-range params do NOT reject the recommendation — guard overrides with
# the default and emits a warning, so Role C always receives valid params.
PARAM_RANGES = {
    "FCFS": {},
    "RR": {"quantum": (1, 100)},
    "PRIORITY": {"aging_threshold": (1, 10000)},
    "MLFQ": {
        "queues": (2, 5),
        "aging_threshold": (1, 10000),
        "boost_interval": (10, 10000),
        # quantum is a list — checked separately
    },
    # SJF/SRTF use a predicted-burst estimator (exponential averaging).
    # The LLM only tunes the predictor; the kernel never sees future bursts.
    "SJF": {
        "alpha_percent": (0, 100),
        "initial": (1, 100000),
        "min": (1, 100000),
        "max": (1, 100000),
    },
    "SRTF": {
        "alpha_percent": (0, 100),
        "initial": (1, 100000),
        "min": (1, 100000),
        "max": (1, 100000),
    },
}

DEFAULT_PARAMS = {
    "FCFS": {},
    "RR": {"quantum": 10},
    "PRIORITY": {"aging_threshold": 100},
    "MLFQ": {
        "queues": 3,
        "quantum": [2, 4, 8],
        "aging_threshold": 100,
        "boost_interval": 100,
    },
    "SJF": {"alpha_percent": 50, "initial": 10, "min": 1, "max": 100},
    "SRTF": {"alpha_percent": 50, "initial": 10, "min": 1, "max": 100},
}

MLFQ_QUANTUM_RANGE = (1, 100)
PREDICTOR_ALGORITHMS = ("SJF", "SRTF")


def _default_mlfq_quantum(queues: int) -> list[int]:
    """A safe per-queue time-slice list whose length == `queues`.

    Geometric 2,4,8,16,32 (so queues=3 reproduces the canonical [2,4,8]),
    each clamped into MLFQ_QUANTUM_RANGE. Used when the LLM's quantum is
    missing/invalid/length-mismatched so the result always stays internally
    consistent with `queues` (never a fixed length-3 default against queues!=3).
    """
    lo, hi = MLFQ_QUANTUM_RANGE
    return [min(max(2 ** (i + 1), lo), hi) for i in range(max(1, queues))]

# Context-aware fallback selection
# If we must reject, what's the best alternative given the metric?
# Fallbacks stay within the stable, non-predictive algorithms (RR/MLFQ) so a
# rejection never lands on a predictor that itself needs tuning.
FALLBACK_BY_METRIC = {
    "response_time": "MLFQ",
    "turnaround_time": "MLFQ",
    "waiting_time": "MLFQ",
    "throughput": "RR",
    "starvation": "MLFQ",  # aging prevents starvation
    "fairness": "RR",  # time-slicing is the fairness baseline
}


class GuardError(RuntimeError):
    """Raised when guard validation fails critically."""


def load_recommendation(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(
            f"[algorithm_guard] recommendation.json not found: {path}\n"
            f"  Run tools/llm_advisor.py first to generate it."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[algorithm_guard] {path} is not valid JSON: {exc}")
    return data


def validate_schema(rec: dict) -> tuple[bool, Optional[str]]:
    """Check that required fields exist and have correct types.
    Returns (is_valid, error_message).
    """
    if not isinstance(rec, dict):
        return False, f"Input is not a JSON object: {type(rec)}"

    if "algorithm" not in rec:
        return False, "Missing required field: 'algorithm'"
    if not isinstance(rec["algorithm"], str):
        return False, f"'algorithm' must be string, got {type(rec['algorithm'])}"

    if "reason" not in rec:
        return False, "Missing required field: 'reason'"
    if not isinstance(rec["reason"], str) or not rec["reason"].strip():
        return False, "'reason' must be a non-empty string"

    if "target_metric" in rec and rec["target_metric"] is not None:
        if not isinstance(rec["target_metric"], str):
            return False, f"'target_metric' must be string, got {type(rec['target_metric'])}"

    if "confidence" in rec and rec["confidence"] is not None:
        if not isinstance(rec["confidence"], (int, float)):
            return False, (
                f"'confidence' must be number between 0 and 1, got {type(rec['confidence'])}"
            )
        if not (0 <= rec["confidence"] <= 1):
            return False, f"'confidence' out of range [0, 1]: {rec['confidence']}"

    return True, None


def normalize_algorithm(algo: str) -> Optional[str]:
    """Normalize algorithm name to uppercase. Return normalized or None if invalid."""
    algo = str(algo).strip().upper()
    if algo in SUPPORTED_ALGORITHMS:
        return algo
    return None


def normalize_metric(metric: str) -> Optional[str]:
    """Normalize metric name, apply aliases. Return normalized or None if invalid."""
    metric = str(metric).strip().lower()

    if metric in METRIC_ALIASES:
        metric = METRIC_ALIASES[metric]

    if metric in SUPPORTED_METRICS:
        return metric

    return None


def check_algorithm(rec: dict) -> str:
    """Validate algorithm. Returns normalized name or raises GuardError."""
    algo = rec.get("algorithm", "").strip()
    normalized = normalize_algorithm(algo)

    if normalized is None:
        raise GuardError(
            f"Algorithm '{algo}' is not supported. Must be one of {SUPPORTED_ALGORITHMS}."
        )

    return normalized


def check_metric(rec: dict) -> tuple[str, Optional[str]]:
    """Validate metric. Returns (metric, info_message or None).

    An unknown metric does NOT reject the recommendation: the algorithm and its
    params may still be perfectly valid, we just can't score the metric fit. We
    downgrade to "unspecified" (skips the compatibility check) and warn, so a
    new metric word from upstream never sinks a sound recommendation.
    """
    metric = rec.get("target_metric")

    if metric is None or metric == "unspecified":
        return "unspecified", "target_metric not specified; cannot validate algorithm-metric fit."

    metric_str = str(metric).strip()
    normalized = normalize_metric(metric_str)

    if normalized is None:
        return "unspecified", (
            f"Unknown target_metric {metric_str!r} (not in {SUPPORTED_METRICS}); "
            f"skipping algorithm-metric compatibility check."
        )

    return normalized, None


def normalize_params(algo: str, params: Any) -> tuple[dict, list[str]]:
    """Validate user params for `algo` and merge with defaults.

    Strategy: out-of-range or missing values are silently replaced with the
    safe default. Each substitution adds a warning message.
    """
    warnings: list[str] = []
    defaults = DEFAULT_PARAMS.get(algo, {})

    if params is None:
        params = {}
    elif not isinstance(params, dict):
        warnings.append(
            f"'params' must be an object; got {type(params).__name__}. Using defaults."
        )
        return dict(defaults), warnings

    if algo == "FCFS":
        if params:
            warnings.append(
                f"FCFS does not accept parameters; ignoring {sorted(params)}."
            )
        return {}, warnings

    ranges = PARAM_RANGES.get(algo, {})
    out = dict(defaults)

    for key, val in params.items():
        # MLFQ.quantum is a list and validated separately
        if algo == "MLFQ" and key == "quantum":
            continue
        if key not in ranges:
            warnings.append(f"{algo}: unknown param '{key}' ignored.")
            continue
        lo, hi = ranges[key]
        if not isinstance(val, int) or isinstance(val, bool) or not (lo <= val <= hi):
            warnings.append(
                f"{algo}.{key}={val!r} out of range [{lo}, {hi}]; "
                f"using default {defaults[key]}."
            )
            continue
        out[key] = val

    if algo == "MLFQ":
        q = params.get("quantum")
        q_lo, q_hi = MLFQ_QUANTUM_RANGE
        if q is None:
            pass  # length reconciled below against out["queues"]
        elif not isinstance(q, list) or not all(
            isinstance(v, int) and not isinstance(v, bool) and q_lo <= v <= q_hi
            for v in q
        ):
            warnings.append(
                f"MLFQ.quantum={q!r} invalid (must be list of ints in "
                f"[{q_lo}, {q_hi}]); using default for queues={out['queues']}."
            )
        elif len(q) != out["queues"]:
            warnings.append(
                f"MLFQ.quantum length {len(q)} != queues {out['queues']}; "
                f"using default for queues={out['queues']}."
            )
        else:
            out["quantum"] = q
        # Reconcile: the seeded default quantum is [2,4,8] (length 3). If queues
        # was set to a non-default value (or quantum fell back above), the length
        # must still equal queues — otherwise an inconsistent MLFQ config reaches
        # the backend. Regenerate a length-correct default in that case.
        if len(out.get("quantum") or []) != out["queues"]:
            out["quantum"] = _default_mlfq_quantum(out["queues"])

    if algo in PREDICTOR_ALGORITHMS:
        # Cross-field rules the per-key range check can't catch.
        if out["min"] > out["max"]:
            warnings.append(
                f"{algo}: min ({out['min']}) > max ({out['max']}); "
                f"resetting both to defaults [{defaults['min']}, {defaults['max']}]."
            )
            out["min"] = defaults["min"]
            out["max"] = defaults["max"]
        if not (out["min"] <= out["initial"] <= out["max"]):
            clamped = max(out["min"], min(out["initial"], out["max"]))
            warnings.append(
                f"{algo}.initial={out['initial']} outside [min, max]="
                f"[{out['min']}, {out['max']}]; clamped to {clamped}."
            )
            out["initial"] = clamped

    return out, warnings


def compatibility_score(algo: str, metric: str) -> float:
    """Return algorithm-metric compatibility score. 0.5 if metric unspecified."""
    if metric == "unspecified":
        return 0.5
    return COMPATIBILITY_MATRIX.get(algo, {}).get(metric, 0.5)


def decide(
    algo: str,
    metric: str,
    compat_score: float,
    confidence: Optional[float],
    metric_info: Optional[str],
) -> tuple[str, list[str]]:
    """Decide guard_result and collect warnings/errors.

    Returns (result, messages) where result is one of:
      - "accepted"              : all checks passed
      - "accepted_with_warning" : passes but with caveats
      - "rejected"              : compatibility below reject threshold (or an
                                  unsupported algorithm/metric). Confidence is
                                  informational and never rejects.
    """
    messages: list[str] = []
    rejected = False

    if metric_info:
        messages.append(metric_info)

    # Compatibility (only meaningful when metric is specified)
    if metric != "unspecified":
        if compat_score < COMPAT_REJECT_THRESHOLD:
            messages.append(
                f"Algorithm {algo} is incompatible with metric {metric} "
                f"(score={compat_score} < {COMPAT_REJECT_THRESHOLD})."
            )
            rejected = True
        elif compat_score < COMPAT_WARN_THRESHOLD:
            messages.append(
                f"Algorithm {algo} is acceptable but not ideal for {metric} "
                f"(score={compat_score})."
            )

    # Confidence — INFORMATIONAL ONLY. The guard validates the INPUT FORMAT
    # (schema, algorithm support, parameter ranges, metric compatibility), NOT
    # the model's self-reported confidence. A low confidence number must never
    # by itself reject an otherwise-valid recommendation (an honestly-uncertain
    # but correct pick would be thrown away). We surface it as a warning for
    # observability only; it does NOT set `rejected`.
    if confidence is None:
        messages.append("Confidence not specified; assumed 0.5.")
    elif confidence < CONFIDENCE_WARN_THRESHOLD:
        messages.append(
            f"Low confidence ({confidence}); informational only — "
            f"not a rejection criterion."
        )

    if rejected:
        return "rejected", messages
    if messages:
        return "accepted_with_warning", messages
    return "accepted", []


def choose_fallback(metric: str, current_algo: str) -> str:
    """Choose fallback algorithm based on metric and current choice.

    Strategy:
      1. If metric-specific fallback exists, use it (unless it's current_algo)
      2. Otherwise fallback to RR (safest baseline)
    """
    if metric in FALLBACK_BY_METRIC:
        fallback = FALLBACK_BY_METRIC[metric]
        if fallback != current_algo:
            return fallback

    return "RR"  # ultimate safe fallback


def _add_compat_keys(decision: dict, rec: dict, *, fallback_used: bool) -> dict:
    """Augment a guard_decision dict with dashboard data-contract keys WITHOUT
    removing any legacy keys.

    Adds:
      - scheduling_algorithm   : DISPLAY form of the CHOSEN algo (fallback when
                                 rejected, otherwise the validated algorithm).
      - original_recommendation: DISPLAY form of what the LLM recommended.
      - fallback_used          : True when rejected / a fallback was applied.
      - target_metric          : canonical key (avg_response_time, ...).

    The internal `algorithm`/`target_metric` validation values are left intact;
    we only add canonical mirrors so the dashboard reads consistent spellings.
    """
    rec = rec or {}
    # Chosen algo: prefer the fallback when one was applied, else the validated.
    chosen = decision.get("fallback_algorithm") or decision.get("algorithm")
    decision["scheduling_algorithm"] = normalize_algorithm_name(chosen)

    orig = rec.get("recommended_scheduling_algorithm") or rec.get("algorithm")
    decision["original_recommendation"] = normalize_algorithm_name(orig)

    decision["fallback_used"] = bool(
        fallback_used or decision.get("fallback_algorithm")
    )

    # Canonical metric mirror (internal validation already used response_time form).
    metric = decision.get("target_metric") or rec.get("target_metric")
    if metric and metric != "unspecified":
        decision["target_metric"] = normalize_target_metric(metric)
    return decision


# Defense-in-depth bounds for LLM-supplied predicted bursts. Mirrors
# tools/llm_advisor._clamp_burst so the guard catches bypass paths
# (callers writing recommendation.json by hand, or future model versions).
_GUARD_PB_MIN = 1
_GUARD_PB_MAX = 100


def _guard_clamp_predicted_bursts(items) -> tuple[list, list[str]]:
    """Re-validate recommendation.predicted_bursts at the guard layer.

    Returns (clean_list, warnings). Drops malformed entries; dedups by pid
    (last wins); clamps every numeric burst to [_GUARD_PB_MIN,_GUARD_PB_MAX]
    so a wild value cannot reach the SJF/SRTF predictor state.
    """
    if not isinstance(items, list):
        return [], []
    warnings: list[str] = []
    by_pid: dict = {}
    for it in items:
        if not isinstance(it, dict):
            warnings.append(f"guard: dropped non-object predicted_bursts entry: {it!r}")
            continue
        pid = it.get("pid")
        if not isinstance(pid, int):
            warnings.append(f"guard: dropped predicted_bursts entry with non-int pid: {pid!r}")
            continue
        out: dict = {"pid": pid}
        pb = it.get("predicted_burst")
        if isinstance(pb, (int, float)):
            v = int(round(float(pb)))
            cv = max(_GUARD_PB_MIN, min(_GUARD_PB_MAX, v))
            if cv != v:
                warnings.append(f"guard: pid={pid} predicted_burst clamped {v} -> {cv}")
            out["predicted_burst"] = cv
        pb_list = it.get("predicted_bursts")
        if isinstance(pb_list, list):
            cleaned = []
            for x in pb_list:
                if not isinstance(x, (int, float)):
                    continue
                v = int(round(float(x)))
                cv = max(_GUARD_PB_MIN, min(_GUARD_PB_MAX, v))
                if cv != v:
                    warnings.append(f"guard: pid={pid} predicted_bursts[i] clamped {v} -> {cv}")
                cleaned.append(cv)
            if cleaned:
                out["predicted_bursts"] = cleaned
        if "predicted_burst" not in out and "predicted_bursts" not in out:
            continue
        if isinstance(it.get("confidence"), (int, float)):
            c = max(0.0, min(1.0, float(it["confidence"])))
            out["confidence"] = round(c, 3)
        if isinstance(it.get("basis"), str):
            out["basis"] = it["basis"][:200]
        by_pid[pid] = out  # dedup last-wins
    return list(by_pid.values()), warnings


def guard(rec: dict) -> dict:
    """Run all guard validations. Returns guard_decision dict.

    `guard_result` values: "accepted" | "accepted_with_warning" | "rejected".
    The dashboard treats "accepted_with_warning" the same as "accepted".
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # Layer 1: Schema
    schema_ok, schema_err = validate_schema(rec)
    if schema_err:
        decision = {
            "guard_result": "rejected",
            "reason": f"Schema validation failed: {schema_err}",
            "algorithm": rec.get("algorithm", "unknown"),
            "fallback_algorithm": "RR",
            "params": dict(DEFAULT_PARAMS["RR"]),
            "_meta": {
                "source": "tools/algorithm_guard.py",
                "generated_at": timestamp,
            },
        }
        return _add_compat_keys(decision, rec, fallback_used=True)

    try:
        # Layer 2: Algorithm
        algo = check_algorithm(rec)

        # Layer 3: Metric
        metric, metric_info = check_metric(rec)

        # Layer 4: Compatibility score
        compat_score = compatibility_score(algo, metric)

        # Layer 5: Confidence
        confidence = rec.get("confidence")

        # Layer 6: Params (override out-of-range with defaults, never reject)
        params, param_warnings = normalize_params(algo, rec.get("params"))

        # Decide
        result, messages = decide(algo, metric, compat_score, confidence, metric_info)
        messages.extend(param_warnings)

        # If we ended up "accepted" with only param warnings, upgrade to warn.
        if result == "accepted" and param_warnings:
            result = "accepted_with_warning"

        # Defense-in-depth: re-clamp / dedup predicted_bursts from the
        # recommendation. Advisor already validates, but the guard re-checks
        # so a hand-written or future-model recommendation cannot smuggle
        # negative / huge / duplicate hints into the scheduler.
        pb_clean, pb_warnings = _guard_clamp_predicted_bursts(rec.get("predicted_bursts"))
        # For SJF/SRTF, declare the prediction source so downstream
        # (orchestrator / xv6) can route hints correctly. If no hints
        # arrived, fall back to EMA explicitly rather than silently.
        prediction_source = None
        if algo in PREDICTOR_ALGORITHMS:
            prediction_source = "llm" if pb_clean else "ema"
            if not pb_clean:
                pb_warnings.append(
                    f"{algo} without predicted_bursts -> EMA fallback (xv6 default predictor)."
                )
        if pb_warnings:
            messages.extend(pb_warnings)
            if result == "accepted":
                result = "accepted_with_warning"

        # Build output. `confidence_score` always carries a usable number
        # (assumed 0.5 when the LLM omitted it) so reason strings and the
        # downstream dashboard never see a literal "None".
        effective_confidence = confidence if confidence is not None else 0.5
        guard_decision: dict[str, Any] = {
            "guard_result": result,
            "algorithm": algo,
            "params": params,
            "target_metric": metric,
            "compatibility_score": compat_score,
            "confidence_score": effective_confidence,
            "predicted_bursts": pb_clean,
            "prediction_source": prediction_source,
        }

        if result == "accepted":
            guard_decision["reason"] = (
                f"Accepted: {algo} is suitable for {metric} "
                f"(compat={compat_score:.2f}, confidence={effective_confidence:.2f})."
            )
        elif result == "accepted_with_warning":
            guard_decision["reason"] = (
                f"Accepted with warnings: {algo} for {metric} "
                f"(compat={compat_score:.2f}, confidence={effective_confidence:.2f})."
            )
            guard_decision["warnings"] = messages
        else:  # rejected
            fallback = choose_fallback(metric, algo)
            guard_decision["fallback_algorithm"] = fallback
            # Replace params with fallback's defaults
            guard_decision["params"] = dict(DEFAULT_PARAMS.get(fallback, {}))
            guard_decision["reason"] = (
                f"Rejected {algo} for {metric}: {'; '.join(messages)}. "
                f"Falling back to {fallback}."
            )
            guard_decision["warnings"] = messages

        guard_decision["_meta"] = {
            "source": "tools/algorithm_guard.py",
            "generated_at": timestamp,
            "recommendation_source": "recommendation.json",
        }

        return _add_compat_keys(
            guard_decision, rec, fallback_used=(result == "rejected")
        )

    except GuardError as exc:
        fallback = choose_fallback(
            rec.get("target_metric", "response_time"),
            rec.get("algorithm", "UNKNOWN"),
        )
        decision = {
            "guard_result": "rejected",
            "reason": f"Guard validation failed: {exc}",
            "algorithm": rec.get("algorithm", "unknown"),
            "fallback_algorithm": fallback,
            "params": dict(DEFAULT_PARAMS.get(fallback, {})),
            "_meta": {
                "source": "tools/algorithm_guard.py",
                "generated_at": timestamp,
            },
        }
        return _add_compat_keys(decision, rec, fallback_used=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Algorithm Guard (Role B)")
    parser.add_argument(
        "--in",
        dest="in_path",
        default=str(PROJECT_ROOT / "outputs" / "recommendation.json"),
        help="path to recommendation.json",
    )
    parser.add_argument(
        "--out",
        dest="out_path",
        default=str(PROJECT_ROOT / "outputs" / "guard_decision.json"),
        help="path to write guard_decision.json",
    )
    args = parser.parse_args()

    rec = load_recommendation(Path(args.in_path))
    decision = guard(rec)

    out_path = Path(args.out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(decision, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    result = decision.get("guard_result", "unknown")
    algo = decision.get("algorithm", "unknown")
    fallback_info = f" → fallback: {decision.get('fallback_algorithm')}" if result == "rejected" else ""
    print(f"[algorithm_guard] {result.upper()} (algo={algo}){fallback_info} → {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
