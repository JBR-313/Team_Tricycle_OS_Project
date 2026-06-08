# experiments/ — research & evidence tools (NOT the pipeline)

These scripts answer the project's two evaluation questions — **"does the LLM
make a good choice?"** and **"does feedback improve it?"** — by *measuring* them.
They are run by hand to produce evidence in `outputs/`; they are **not** part of
the running scheduling pipeline. The pipeline lives in [`../tools/`](../tools).

> If you are reading the repo to understand the system, start with
> [`../tools/`](../tools) and [`../scripts/orchestrator.py`](../scripts/orchestrator.py).
> This folder is supporting evidence.

| script | question it answers | output |
|---|---|---|
| `burst_ablation.py` | Is the LLM's cold-start burst **prediction** better than a blind EMA / a fixed heuristic? | `outputs/ablation/burst_ablation.{json,md}` |
| `burst_xv6_confirm.py` | Do those burst priors actually **improve SJF/SRTF** on the **real xv6 kernel**? (The simulator A/B `burst_scheduling_eval.py` was removed with the simulator; the xv6 run is now reproducible — deterministic `-icount` + fixed-iteration bursts — so this is the live path to a real-kernel number.) | `outputs/ablation/` |
| `outcome_store.py` | Retrieval memory: visible features → measured-best algorithm (leakage-free, leave-one-out). | (library, used by the two below) |
| `retrieval_advisor.py` | Does retrieving similar **measured precedents** improve the recommendation? | `outputs/learning/llm_cache/` |
| `recommendation_eval.py` | Leave-one-out cross-validation of every recommendation mode (fixed / kNN / LLM ± retrieval). | `outputs/learning/recommendation_eval.json` + `RESULTS.md` |

## Honesty contract
Same as the rest of the project: future CPU bursts and `expected_best_algorithm`
are read **only** by the offline evaluator to score/judge — never placed in a
prompt. Predictions and recommendations see visible features only.

## Running
All scripts add `../tools` (core modules) and this directory (siblings) to
`sys.path`, so run them from anywhere:

```bash
python3 experiments/burst_ablation.py            # offline re-score from cache
python3 experiments/burst_ablation.py --advise   # elicit fresh (needs UPSTAGE_API_KEY)
python3 experiments/recommendation_eval.py --offline
```
