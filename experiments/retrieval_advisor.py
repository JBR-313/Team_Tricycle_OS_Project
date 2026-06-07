#!/usr/bin/env python3
"""retrieval_advisor.py — recommend a scheduling algorithm with OPTIONAL
retrieval of measured precedents (the proposed learning mechanism).

Two modes:
  use_retrieval=False : the current advisor — xv6 facts only, reasons blind.
  use_retrieval=True  : xv6 facts + the k most similar PAST workloads and the
                        algorithm that actually won on them (from outcome_store).
                        This is the "evaluate -> feedback -> improve" loop made
                        concrete: the advisor learns from accumulated measured
                        outcomes instead of a one-shot majority-biased rule file.

Honesty: the user prompt is built by tools/llm_advisor.build_user_prompt, which
already strips the query's own expected_best_algorithm, total_cpu_work, and
per-process labels. Retrieved examples carry only VISIBLE features of OTHER
workloads + their measured winner. Leave-one-out (exclude_name) guarantees a
workload never sees its own answer.

Responses are cached under outputs/learning/llm_cache/ so the leave-one-out
sweep is cheap to re-run and stays deterministic across reruns.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))           # core pipeline modules
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling experiments/

import outcome_store as osmod  # noqa: E402
from workload_analyzer import analyze_workload, load_workload  # noqa: E402
import llm_advisor as la  # noqa: E402
from solar_client import SolarClient, SolarError  # noqa: E402

WORKLOADS_DIR = PROJECT_ROOT / "workloads"
CACHE_DIR = PROJECT_ROOT / "outputs" / "learning" / "llm_cache"

_RETRIEVAL_HEADER = """

=== RETRIEVED PRECEDENTS — past workloads with SIMILAR visible features and the
algorithm that ACTUALLY WON when measured on THIS xv6 backend ===
Treat these as empirical evidence, not an answer key. Reason about WHICH visible
features (process count, arrival gaps, priority spread, interactive ratio, ...)
separate the RR-winners from the MLFQ-winners, then apply that reasoning to the
current workload. Do NOT blindly copy the nearest one; the current workload may
differ on the feature that flips the outcome.
"""


def _summary_for(name: str) -> dict:
    path = WORKLOADS_DIR / f"{name}.json"
    return analyze_workload(load_workload(path), path)


def build_system_prompt(neighbors: list[dict] | None) -> str:
    # facts-only baseline (feedback_path=None keeps the legacy rule file OUT).
    prompt = la.build_system_prompt(None)
    if neighbors:
        prompt += _RETRIEVAL_HEADER + osmod.format_examples_for_prompt(neighbors) + "\n"
    return prompt


def _algo_of(rec: dict, summary: dict) -> str:
    validated = la.validate(rec, summary=summary)
    return la.normalize_algorithm_name(validated.get("algorithm")).upper()


def recommend(name: str, store: list[dict], k: int, use_retrieval: bool,
              rep: int = 0) -> str | None:
    """One recommendation for workload `name`. Returns the UPPERCASE canonical
    algorithm (e.g. 'MLFQ', 'RR') or None on failure."""
    summary = _summary_for(name)
    neighbors = None
    if use_retrieval:
        qf = osmod.prompt_safe_features(summary)
        neighbors = osmod.retrieve(qf, store, k, exclude_name=name)
    system_prompt = build_system_prompt(neighbors)
    user_prompt = la.build_user_prompt(summary)
    client = SolarClient()
    # temperature 0.0 for determinism; rep varies only to average API noise.
    raw = client.complete_json(prompt=user_prompt, system=system_prompt,
                               temperature=0.0)
    return _algo_of(raw, summary)


def _cache_path(name: str, use_retrieval: bool, k: int, rep: int) -> Path:
    mode = f"ret_k{k}" if use_retrieval else "facts"
    return CACHE_DIR / f"{name}__{mode}__rep{rep}.json"


def recommend_cached(rec: dict, store: list[dict], k: int, use_retrieval: bool,
                     reps: int = 1) -> str | None:
    """Cached, majority-voted recommendation for leave-one-out. `rec` is an
    outcome_store record (has 'name'). Caches each rep's raw choice."""
    name = rec["name"]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    choices: list[str] = []
    for r in range(reps):
        cp = _cache_path(name, use_retrieval, k, r)
        if cp.is_file():
            cached = json.loads(cp.read_text()).get("algo")
            if cached:
                choices.append(cached)
                continue
        try:
            algo = recommend(name, store, k, use_retrieval, rep=r)
        except SolarError as exc:
            print(f"  [warn] {name} rep{r}: {exc}")
            algo = None
        if algo:
            cp.write_text(json.dumps({"name": name, "use_retrieval": use_retrieval,
                                      "k": k, "rep": r, "algo": algo}) + "\n")
            choices.append(algo)
    if not choices:
        return None
    # majority vote (ties -> first seen, i.e. lowest rep)
    counts: dict[str, int] = {}
    for c in choices:
        counts[c] = counts.get(c, 0) + 1
    return max(choices, key=lambda c: (counts[c], -choices.index(c)))


if __name__ == "__main__":
    # quick single-workload smoke
    name = sys.argv[1] if len(sys.argv) > 1 else "xv6_cpu_bound"
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    store = osmod.build_store(source_filter="xv6-measured")
    print("facts-only :", recommend(name, store, k, use_retrieval=False))
    print("retrieval  :", recommend(name, store, k, use_retrieval=True))
