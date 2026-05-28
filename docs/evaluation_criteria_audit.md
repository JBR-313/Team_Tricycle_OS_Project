# Evaluation Criteria Audit — Trace-based LLM Recommendation Judging

> **Scope:** Whether `tools/metrics.py`'s `compute_judgment()` is a sound
> evaluator for the LLM's algorithm recommendation, and why each threshold is
> the value it is. Code reference: `tools/metrics.py:414-489`. Status:
> 2026-05-28, branch `feat/upstage-runtime-strict`.

---

## 1. Is trace-based metrics evaluation appropriate?

**Yes, but with caveats — and we already use the right caveats.** The
recommendation we evaluate is *“which algorithm best fits this workload on
this target metric.”* That question is only answerable after the algorithm
has actually run, which is exactly what `trace_<algo>.jsonl` records. The
evaluator therefore:

1. Runs **all six algorithms** on the *same deterministic workload* (same
   seed + profile in `schedtest`, or the same `processes` list in the
   simulator). `scripts/orchestrator.py` enforces this by executing every
   algorithm sequentially, **LLM-selected first** (`docs/orchestrator_design.md`).
2. Computes metrics from the trace **independently of the LLM** —
   `tools/metrics.py` rebuilds per-process timelines from `ARRIVE` /
   `DISPATCH` / `EXIT` events; the LLM has no editorial influence on the
   numbers.
3. Compares the LLM's algorithm to the rest on the *target metric the LLM
   itself declared* (`recommendation.json:target_metric`). This catches both
   “picked the wrong algorithm” and “picked an algorithm whose target metric
   was the wrong one to optimize.”

What this **doesn't** answer:

- “Is the LLM's *reason* good?” — we evaluate the outcome, not the prose.
- “Is the recommendation robust across seeds?” — current
  `orchestrator.py` runs a single seed per profile. (Future: multi-seed
  rollup.)
- “Is this score generalizable beyond the curated `schedtest` workloads?”
  — see `docs/workload_coverage_matrix.md`.

These limits are acceptable for an educational lab, and they are surfaced in
the dashboard `RecommendationEvidence` card.

---

## 2. The three judgments

`tools/metrics.py:457-467`

```python
def compute_judgment(regret_score, starvation_occurred):
    if starvation_occurred:
        return "FAIL"
    if regret_score is None:
        return "UNKNOWN"
    if regret_score <= SUCCESS_REGRET:        # 0.10
        return "SUCCESS"
    if regret_score <= NEAR_SUCCESS_REGRET:   # 0.25
        return "NEAR-SUCCESS"
    return "FAIL"
```

| Verdict | Condition (target metric, lower-is-better example) | Meaning |
|---|---|---|
| **SUCCESS** | regret ≤ 0.10 | LLM's algorithm is within 10% of the best observed on the target metric. |
| **NEAR-SUCCESS** | 0.10 < regret ≤ 0.25 | LLM picked a defensible algorithm (within 30%), but not the optimum. |
| **FAIL** | regret > 0.25, **or** starvation occurred on the LLM-selected run | Recommendation is materially worse, or it caused a safety problem. |
| **UNKNOWN** | regret cannot be computed (no baseline, or metric absent) | Fallback; should be rare since `_make_synthetic_rr_baseline()` provides a baseline when no other trace exists. |

---

## 3. Where the thresholds come from

### 3.1 `SUCCESS_REGRET = 0.10`

A 10% gap is the conventional “noise floor” used in scheduling pedagogy and
in textbooks like Silberschatz when comparing scheduling algorithms on small
workloads. With curated workloads of 5 processes and bursts in the 1–60 tick
range:

- A 1-tick rounding error on a 10-tick metric is **10%** — so anything below
  this is indistinguishable from quantization noise.
- The compatibility matrix in `tools/algorithm_guard.py:66-115` deliberately
  spreads algorithm scores in 0.1 increments. SUCCESS at 0.10 keeps the
  evaluator and the guard at the same resolution.

### 3.2 `NEAR_SUCCESS_REGRET = 0.25`

A 30% gap is the practical threshold above which a different algorithm
would *visibly* win the comparison on the Gantt chart. Empirically, with the
curated `schedtest` profiles, MLFQ vs FCFS on `interactive` shows ~10×
response-time difference — regret ≈ 9.0 — so any LLM choice that lands
within 0.25 is in the same algorithmic family as the winner. Above 0.25 the
audience can spot the wrong choice on screen, which is precisely when we
want the verdict to flip to FAIL.

### 3.3 Why thresholds are constants, not data-driven

In an educational tool, constants are easier to defend than learned
percentiles:

- Reproducible — same inputs always produce the same verdict.
- Inspectable — one grep gives the rule.
- Decoupled from the workload — adding a new profile does not silently move
  the SUCCESS bar.

Changing them is a deliberate change of grading rubric, which is what we
want.

---

## 4. The starvation override

`tools/metrics.py:457-460`

```python
if starvation_occurred:
    return "FAIL"
```

This *forces* FAIL regardless of regret.

### 4.1 Why an override is needed

Regret is a single-number summary of *one* metric. A recommendation can be
near-optimal on `avg_response_time` and yet leave a low-priority process
waiting indefinitely. In OS pedagogy, that is the textbook failure mode of
naive Priority — a 0% regret on response time with a starved P5 is the
*worst* outcome we can demonstrate, not a near-success.

### 4.2 How starvation is detected

`tools/metrics.py:14-20`

```python
# Starvation rule has TWO conjunctive thresholds:
#   1. Relative: waited > STARVATION_MULTIPLIER * avg_waiting_time
#   2. Absolute: waited >= MIN_STARVATION_WAIT_TICKS
# Both must hold. The relative rule alone is unstable on tiny xv6 traces:
# e.g. avg_wait=0.2, max_wait=1 -> 1 > 0.6 wrongly flags a 1-tick wait as
# starvation. Adding an absolute floor (default 5 ticks) means short xv6
# workloads with trivial waits no longer FAIL, while genuine starvation in
# longer simulator runs (where waits are tens of ticks) still triggers.
STARVATION_MULTIPLIER = 3
MIN_STARVATION_WAIT_TICKS = 5
```

This was strengthened in PR #14 (`fix(metrics): add absolute floor to
starvation rule for short xv6 traces`). The conjunctive rule means:

- Long simulator runs still catch genuine starvation (waits of tens/hundreds
  of ticks). 
- Short xv6 `schedtest` runs (5 processes, ~30–80 events) do not get false
  FAILs from a single 1-tick outlier.

### 4.3 Why FAIL and not “warning”

The verdict is binary in the LLM advisor’s loop: SUCCESS/NEAR-SUCCESS leaves
`feedback_rules.md` untouched; **FAIL triggers prompt feedback**. A
starvation outcome is a clear teaching moment that should feed back into the
LLM’s next prompt (“avoid Priority without strong aging when priority
variance > X”). The override therefore drives the right pedagogical loop, not
just the right label.

---

## 5. Regret formula

`tools/metrics.py:414-454`

- Lower-is-better metric: `regret = (llm − best) / best`
- Higher-is-better metric (`throughput`): `regret = (best − llm) / best`
- Negative regret clamped to 0.0.
- `best` chosen from all observed algorithms’ values on `target_metric`,
  including the LLM’s own (so regret is always ≥ 0).
- When no comparison is available, `tools/metrics.py:695-797`
  `_make_synthetic_rr_baseline()` estimates an RR run from the LLM-run's own
  per-process data so a baseline always exists.

PR #15 (`fix(judgment): add absolute floor to regret denominator on
tick-granular metrics`) prevents division-by-tiny-number blow-ups on metrics
that can legitimately be 0 or 1.

---

## 6. Threats to validity

| Threat | Mitigation in place | Residual risk |
|---|---|---|
| Single-seed run; LLM might be lucky/unlucky | Same seed across all algorithms makes the comparison fair within the run; not across seeds. | Demo currently uses seed 42. Multi-seed rollup is post-demo work. |
| Synthetic RR baseline is itself an estimate | Used only when no real baseline exists; algorithm-only comparison is preferred. | Synthetic baseline can over-estimate RR's response_time on bursty workloads. |
| Simulator SJF/SRTF is oracle (see `sjf_srtf_prediction_audit.md`) | xv6 path uses EMA predictor; final demo uses xv6 backend. | Simulator-side regret for SJF/SRTF is optimistic; do not show as evidence of predictor quality. |
| LLM might game the target_metric (always pick `throughput` to look easy) | Algorithm Guard’s compatibility matrix penalises algorithm-metric mismatches. | Guard is a guardrail, not a proof; spot-check during demo prep. |
| Tiny workloads make regret jittery | Conjunctive starvation rule (PR #14) and regret denominator floor (PR #15). | Cannot fully fix; the cure is bigger workloads (see `workload_coverage_matrix.md`). |

---

## 7. Recommended improvements (post-demo)

1. **Multi-seed evaluation.** Run each profile under 3–5 seeds; report
   median regret and worst-case judgment. Reuses `scripts/multi_profile_demo_check.py`'s
   loop.
2. **Show metric direction on the dashboard.** `EvaluationResult.jsx`
   already does direction-aware comparison; surface the per-metric arrow
   (↓ better / ↑ better) next to each comparison row so the verdict is
   self-explanatory.
3. **Surface starvation cause on FAIL.** When starvation overrides the
   judgment, include `starvation_pids` + the max wait of each in the
   dashboard banner.
4. **Add an UNKNOWN explainer.** Today an UNKNOWN verdict renders as
   “regret_score: null” which is opaque to the audience.

---

## 8. One-paragraph defense

> The verdict is computed from the same trace the audience watches. The
> LLM cannot influence the numbers, only the algorithm choice that produced
> them. SUCCESS at 10% regret and NEAR-SUCCESS at 30% match the resolution
> of the curated workloads and of the algorithm-vs-metric matrix; above 30%,
> the wrong algorithm is visibly wrong on screen. Starvation flips the
> verdict to FAIL regardless of regret because optimizing one metric while
> leaving a process indefinitely waiting is the canonical failure mode the
> course is teaching against — and the same FAIL is what wakes the LLM's
> prompt-feedback loop. The constants are simple, inspectable, decoupled
> from any specific workload, and aligned with the algorithm-vs-metric grid
> the Algorithm Guard already uses.
