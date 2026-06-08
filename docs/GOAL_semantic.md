# GOAL 3 (B) — the LLM's actual lane: natural-language intent → scheduler config

## Why
Our measured negatives show the LLM is NOT a good *quantitative* scheduler
(algorithm pick, mid-run switch, numeric burst prediction — classical methods win;
see [[../docs/GOAL_burst_eval.md]] results). But those experiments deliberately
STRIPPED the semantic channel (`description`/`label`) to be fair to numeric
baselines. The LLM's real, uncontested strength is exactly that channel:
translating free-form human intent — and low-level traces — into/out of OS
scheduling decisions. No numeric heuristic can read English. This goal builds and
HONESTLY evaluates that.

## What
1. **Intent advisor** (`tools/intent_advisor.py`): natural-language workload intent
   (e.g. "interactive desktop, responsiveness matters most") → a guard-valid
   scheduling config {algorithm, target_metric, params, reason}. Reads ONLY the
   human's words; never sees actual bursts.
2. **Honest eval** (`experiments/intent_eval.py`): a rubric of (intent →
   OS-textbook-acceptable algorithm family). The LLM sees only the intent; score
   whether its pick falls in the acceptable family AND passes the Algorithm Guard.
   This is a fair test of "translate intent → sensible, valid config" — a task
   with NO numeric-heuristic baseline, so it is the LLM's uncontested domain.

## Why this is honest (not circular)
The acceptable family is a standard OS rubric (responsiveness→RR/MLFQ;
batch/throughput→FCFS/SJF; importance+no-starvation→PRIORITY+aging/MLFQ;
shortest-first→SJF/SRTF). The LLM never sees the rubric. We grade a translation,
like grading a language test — not "beat a metric" (which is info-bounded on xv6
and already measured negative).

## Done when
- `intent_advisor` maps a NL intent to a guard-VALID config, AND
- `intent_eval` reports, over the rubric set, the intent→family match rate AND
  guard-pass rate (uses the real Solar model; .env key present).
- (demo) one end-to-end NL → config → xv6 run → explanation.

## Honest framing for the report
This does NOT claim the LLM picks the metric-optimal algorithm (we measured it
often can't on xv6). It claims the LLM correctly TRANSLATES human intent into a
valid, sensible configuration and explains the result — the part of "LLM for OS"
that has no classical substitute. Pairs with the negatives as: *"LLM out of the
hot path (it loses there); LLM at the human interface (it wins there)."*
