#!/usr/bin/env python3
"""correction_guard.py — re-validate a preview correction proposal (PREVIEW ONLY).

Reads correction_proposal.json (from tools/correction_proposer.py) and emits
correction_guard_decision.json. Validates:

  1. The proposed algorithm is in SUPPORTED_ALGORITHMS (re-uses
     tools/algorithm_guard.py's table).
  2. Every proposed param is in PARAM_RANGES (re-uses the same table).
  3. The proposal still carries preview_only=true / applied=false (this
     module refuses to validate anything that pretends to be live).

The decision is preview_only=true / applied=false as well; the dashboard
renders it next to the proposal but xv6 is never affected.

Usage:
    python3 tools/correction_guard.py \\
        --proposal outputs/correction_proposal.json \\
        --out      outputs/correction_guard_decision.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Re-use Role B's tables so the new guard cannot drift from the old one.
try:
    from tools.algorithm_guard import PARAM_RANGES, SUPPORTED_ALGORITHMS
except ImportError:  # invoked as `python3 tools/correction_guard.py`
    sys.path.insert(0, str(PROJECT_ROOT / "tools"))
    from algorithm_guard import PARAM_RANGES, SUPPORTED_ALGORITHMS  # type: ignore[no-redef]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _check_quantum(value, rng: tuple[int, int]) -> bool:
    """Quantum may be scalar (RR) or list (MLFQ). Each element must be in range."""
    lo, hi = rng
    if isinstance(value, list):
        return all(isinstance(v, (int, float)) and lo <= v <= hi for v in value) and bool(value)
    if isinstance(value, (int, float)):
        return lo <= value <= hi
    return False


def validate(proposal: dict) -> dict:
    """Return a correction_guard_decision dict. Never raises on bad input."""
    rejected_params: list[str] = []
    reasons: list[str] = []

    # 0. Refuse anything that claims to be live.
    if not (proposal.get("preview_only") is True and proposal.get("applied") is False):
        return {
            "preview_only": True,
            "applied": False,
            "guard_result": "rejected",
            "proposal_source": "correction_proposal.json",
            "reason": "proposal does not carry preview_only=true / applied=false; refusing",
            "_meta": {
                "source": "tools/correction_guard.py",
                "generated_at": _iso_now(),
            },
        }

    prop = proposal.get("proposed") or {}
    new_algo_raw = str(prop.get("new_scheduling_algorithm") or "").upper()
    correction_type = prop.get("correction_type") or ""
    new_params = prop.get("new_params") or {}

    # 1. Algorithm must be supported.
    if correction_type == "no_op":
        # Pass-through; nothing to re-validate.
        return {
            "preview_only": True,
            "applied": False,
            "guard_result": "accepted",
            "proposal_source": "correction_proposal.json",
            "reason": "no-op proposal — nothing to change; trivially accepted",
            "_meta": {
                "source": "tools/correction_guard.py",
                "generated_at": _iso_now(),
            },
        }

    if new_algo_raw not in SUPPORTED_ALGORITHMS:
        reasons.append(f"unsupported algorithm {new_algo_raw!r}")
        rejected_params.append("new_scheduling_algorithm")

    # 2. Param ranges (best-effort; unknown params are surfaced but not fatal).
    algo_ranges = PARAM_RANGES.get(new_algo_raw, {})
    for k, v in new_params.items():
        if k == "quantum" and "quantum" in algo_ranges:
            if not _check_quantum(v, algo_ranges["quantum"]):
                lo, hi = algo_ranges["quantum"]
                reasons.append(f"quantum out of range {v!r} (expected each in [{lo},{hi}])")
                rejected_params.append("quantum")
            continue
        if k == "quantum" and new_algo_raw == "MLFQ":
            # MLFQ uses a list; reasonable per-slot range (1..100) mirrors RR.
            if not _check_quantum(v, (1, 100)):
                reasons.append(f"MLFQ quantum out of range {v!r} (expected each in [1,100])")
                rejected_params.append("quantum")
            continue
        rng = algo_ranges.get(k)
        if rng is None:
            continue  # unknown parameter, leave it alone
        lo, hi = rng
        if not isinstance(v, (int, float)) or not (lo <= v <= hi):
            reasons.append(f"{k}={v!r} out of range [{lo},{hi}]")
            rejected_params.append(k)

    accepted = not reasons
    out: dict = {
        "preview_only": True,
        "applied": False,
        "guard_result": "accepted" if accepted else "rejected",
        "proposal_source": "correction_proposal.json",
        "correction_type": correction_type,
        "new_scheduling_algorithm": new_algo_raw,
        "reason": (
            f"correction validated: {correction_type} on {new_algo_raw}"
            if accepted else "; ".join(reasons)
        ),
        "_meta": {
            "source": "tools/correction_guard.py",
            "generated_at": _iso_now(),
        },
    }
    if not accepted:
        out["rejected_params"] = sorted(set(rejected_params))
        out["fallback"] = {
            "correction_type": "no_op",
            "rationale": "preview retained the original recommendation; xv6 unaffected",
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Re-validate a preview correction proposal against algorithm/param ranges"
    )
    ap.add_argument("--proposal", required=True,
                    help="correction_proposal.json from tools/correction_proposer.py")
    ap.add_argument("--out", required=True,
                    help="output correction_guard_decision.json")
    args = ap.parse_args()

    p = Path(args.proposal)
    if not p.is_file():
        print(f"[correction_guard] no proposal at {p}; nothing to validate.")
        return 0
    proposal = _read_json(p)
    decision = validate(proposal)
    Path(args.out).write_text(json.dumps(decision, indent=2), encoding="utf-8")
    print(f"[correction_guard] wrote {args.out}: {decision['guard_result']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
