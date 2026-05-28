# Verification Progress Log

Per `visual_scheduler_verification_goal.md`. Each loop records: focus,
claims checked, classification (Verified/Partial/False/Broken), fixes,
tests, residual risks, next focus.

---

## Loop 1 — Direction & code-level claim verification (2026-05-28)

### Selected focus
Verify the previous overnight implementation loop's claims (workload
expansion, hidden burst separation, LLM burst prediction, EMA baseline,
regret evaluator, RUN button, tab UI, MLFQ panel) against the actual code
state. Fix the smallest safe set of issues that emerge. Do not add new
features.

### Claims checked

From the previous loop's final report:

1. 10 workloads with v2 metadata (7 spec IDs + 3 bonus)
2. `_pick_sjf` / `_pick_srtf` use `predicted_burst`, never `p.remaining`
3. EMA predictor `(alpha=50, init=10, [1,100])` math correct, update at
   end-of-burst
4. LLM advisor `predicted_bursts[]` validated; advisor prompt doesn't leak
   actual bursts
5. Algorithm guard validates LLM output
6. Evaluator threshold 0.10 / 0.25; orchestrator + simulator + docs aligned
7. Trace parser tolerates new fields (PRED_UPDATE, QUEUE_CHANGE)
8. RUN server end-to-end, single-run lock, offline-fixture fallback,
   localhost-only
9. Dashboard tabs (LLM / Visualization / Evaluation), snapshot UI removed,
   MLFQ panel hides for non-MLFQ algorithms

### Verified

- **V-2 Workloads.** All 10 parse; analyzer reports correct
  `id`/`target_metric`/`expected_best_algorithm` metadata; `PROFILE_MAP`
  covers all 10 + 6 legacy aliases; spec required IDs all present.
- **V-2 Hidden-burst summary leak.** `workload_summary.json` has no
  per-pid `actual_bursts`/`cpu_bursts`/`bursts`. Only the aggregate
  `total_cpu_work` and `burst_count_distribution` survive — both
  workload-level statistics, not per-pid future answers.
- **V-3 Hidden-burst pick path.**
  - `_pick_sjf` body: `key=lambda p: (p.predicted_burst, p.ctime, p.pid)`
  - `_pick_srtf` body uses `p.predicted_burst - p.cur_burst_run`
  - SRTF in-loop preemption check also uses predicted remaining only.
  - `p.remaining` only appears in execution paths
    (init / decrement / burst-end branching).
- **V-4 EMA math.** Predictor formula
  `tau_next = (alpha%*observed + (100-alpha%)*prev) // 100` correct for
  alpha={0, 50, 100}; observed=0 keeps prev; min/max clamps work;
  update only at end-of-burst (`_update_prediction` call in
  `if p.remaining <= 0:` branch and xv6 `update_burst_prediction()`
  inside `sleep()`).
- **V-5 advisor prompt.** `build_user_prompt(summary)` serializes the
  workload_summary, which already excludes per-pid actual bursts.
- **V-6 guard accept paths.** Existing recommendation validation
  pipeline still works for the 6 algorithms.
- **V-8 trace_parser.** PRED_UPDATE / QUEUE_CHANGE / unknown future
  fields all parse correctly. The "carry every remaining token through"
  rule keeps schema-forward-compatible.
- **V-9 run_server.** Health, status, end-to-end (simulator backend +
  offline-fixture), single-run lock (first 202, second 409),
  path traversal blocked (`--path-as-is /../../etc/passwd` -> 400),
  CORS OPTIONS preflight 204, bad backend 400, unknown profile 400.
- **V-10 dashboard build.** `npm run build` produces dist/ (196 KB JS,
  20 KB CSS); MLFQ panel correctly hides for non-MLFQ; snapshot UI
  code paths fully removed.

### Partial / false / broken

- **V-5 BROKEN (FIXED).** `_validate_predicted_bursts` in advisor accepted:
  - duplicate pids (both entries kept)
  - negative `predicted_burst` (e.g. -5 passed through)
  - huge `predicted_burst` (e.g. 1e9 passed through)
  - confidence outside [0,1]
  Spec §7 explicitly required "Out-of-range predictions are handled" —
  partial-false claim. **Fixed** by adding `PREDICTED_BURST_MIN/MAX = 1/100`,
  `_clamp_burst()`, per-pid dedup (last wins), confidence clamp, and
  element-wise clamp inside `predicted_bursts` list.
- **V-6 PARTIAL (FIXED).** `algorithm_guard.py` did **not** validate the
  recommendation's `predicted_bursts[]` at all. Spec §8 required a
  guard-side check. **Fixed** by adding `_guard_clamp_predicted_bursts()`
  + integration in `guard()`: re-clamps to [1,100], dedups, forwards a
  `prediction_source` field (`llm` / `ema` / `null`), and explicitly
  warns when SJF/SRTF arrives with no hints (EMA fallback).
- **V-7 FALSE (FIXED).** `NEAR_SUCCESS_REGRET` constant was 0.25 in
  `tools/metrics.py`, but **`dashboard_live/src/data/schemaCompat.js`**
  still hardcoded 0.30 — meaning the dashboard could compute
  NEAR-SUCCESS while `metrics.json` said FAIL on the same number.
  Also stale: `docs/evaluation_plan.md` (3 sites),
  `docs/dashboard_data_contract.md` (1 site),
  `docs/evaluation_criteria_audit.md` (5 sites — written before the
  threshold change), `tools/README.md` (2 lang sites),
  `tools/llm_advisor.py` (2 docstring sites).
  **Fixed** all to 0.25; kept change-history comments referencing the
  0.30→0.25 bump.
- **V-7 PARTIAL (FIXED).** Regret display for tiny `best` values
  produced text like "regret = 1083.3% (> 25%)" — technically true,
  visually nonsense on a demo screen. **Fixed** by adding a
  presentation-safe ">999% (regret huge because best≈0)" cap in:
  - `tools/metrics.py:_explain_judgment`
  - `tools/scheduler_simulator.py:run_all_algorithms`
  - `scripts/orchestrator.py` inline evaluator
  - `dashboard_live/src/components/EvaluationResult.jsx`
    (percentage display + tooltip with raw value)
- **V-9 BROKEN (FIXED).** 409 (single-run conflict) response body had
  `error: null` because the snapshot was spread AFTER the error
  message in the dict literal, overwriting it. **Fixed** by reversing
  the spread order: `{**STATE.snapshot(), "error": str(exc)}`.

### Fixes made (summary diff)

| File | Change |
|---|---|
| `tools/llm_advisor.py` | `_clamp_burst()`, range clamp, dedup, confidence clamp in `_validate_predicted_bursts`; docstring threshold 0.30 → 0.25 (×2) |
| `tools/algorithm_guard.py` | `_guard_clamp_predicted_bursts()`; guard re-validates + forwards `predicted_bursts`/`prediction_source`; SJF/SRTF without hints → explicit EMA fallback warning |
| `tools/metrics.py` | `_explain_judgment` regret ">999%" cap |
| `tools/scheduler_simulator.py` | run_all_algorithms explanation cap |
| `tools/README.md` | 0.30 → 0.25 (EN + KR) |
| `scripts/orchestrator.py` | inline evaluator explanation cap |
| `scripts/run_server.py` | 409 conflict body `error` not overwritten |
| `dashboard_live/src/data/schemaCompat.js` | judgeForMetric 0.30 → 0.25 |
| `dashboard_live/src/components/EvaluationResult.jsx` | `formatRegretLabel`: 4-decimal float → percent; ">999%" cap with tooltip |
| `docs/evaluation_plan.md` | thresholds 0.30 → 0.25 (table + bullets) |
| `docs/dashboard_data_contract.md` | thresholds 0.30 → 0.25 |
| `docs/evaluation_criteria_audit.md` | thresholds 0.30 → 0.25 (5 sites) |

No file deletions, no kernel/xv6 changes, no new dependencies.

### Tests run

- 10/10 workloads `python3 tools/workload_analyzer.py <file>` exit 0
- `_validate_predicted_bursts` edge cases: 8 assertions (clamps, dedup,
  confidence bounds, non-numeric/non-int pid/expected_pids filter)
- `guard(rec)` SJF with malicious hints → `accepted_with_warning`,
  hints clamped to [1, 100], explicit warnings; SJF without hints
  → `prediction_source=ema` + warning; MLFQ → `prediction_source=None`
- `trace_parser.parse_line` on PRED_UPDATE / QUEUE_CHANGE /
  `future_field=foo` / boot spam → all behave as documented
- run_server: health/status/start, 409 single-run lock, 400 bad
  backend, 400 invalid profile, 400 path traversal, 204 CORS preflight
- End-to-end (simulator + offline-fixture):
  - `ambiguous_mixed` → judgment FAIL, regret 0.725 (72.5%) — both
    Python and JS judges agree
  - `bursty_long_tail` → judgment FAIL, regret 10.833 → explanation
    now reads ">999% (regret huge because best≈0)"
- `npm run build` for `dashboard_live/` exits 0 (56 modules, 196 KB JS)

### Result

All P0 verification items in the goal doc are now either Verified or
Verified-after-fix. Two real demo-risk bugs (dashboard threshold drift,
unbounded LLM-burst values reaching the scheduler) closed. One
presentation-risk display issue (>1000% regret text) closed.

### Remaining risks

1. **Real Solar API response shape not tested** in this loop. All LLM
   tests used `--offline-fixture`. The `predicted_bursts[]` schema is
   structurally validated, but the live model may emit slightly
   different keys (extra properties, slightly different `basis` format).
   Honest wording is in place in the README; manual API check before
   the demo is still required.
2. **xv6+QEMU end-to-end not executed in this loop.** All end-to-end
   verification used the simulator backend. Kernel code wasn't
   touched; the orchestrator's xv6 path should still work, but a teammate
   on a QEMU-capable machine should re-run `multi_profile_demo_check.py`
   before the demo.
3. **xv6 kernel SJF/SRTF predictor does not accept LLM hints today.**
   `set_predictor_params(alpha, initial, min, max)` is the only
   syscall — per-pid hint injection is unimplemented. Simulator + LLM
   hints work; xv6 + LLM hints do not. Documented as such in README §11.2.
4. **Closed-loop runtime correction is still preview-only.** No code
   change touched this; the existing preview labels remain in place.
5. **run_server runs the orchestrator subprocess synchronously without
   timeout.** A hung subprocess could leave state stuck in RUNNING.
   Mitigation: single-run lock prevents pile-up; the dashboard surfaces
   the stuck state via the badge.
6. **dashboard_test (sandbox) not updated.** Still shows the old tab-less
   3-column layout — by design, but presenters should not open it.

### Next recommended focus

1. **(Required before demo)** Real Solar API call: run
   `python3 tools/llm_advisor.py --in outputs/workload_summary.json` with
   a real key, confirm `predicted_bursts[]` round-trips through guard +
   simulator without warnings.
2. **(Required before demo)** xv6+QEMU run on a teammate machine to
   confirm orchestrator `--backend xv6` end-to-end with the new evaluator
   threshold + new `prediction_source` field.
3. (Optional) Add an orchestrator subprocess timeout (e.g. 5 min) so a
   stuck run can recover without restarting the run_server.
4. (Optional) `_validate_predicted_bursts` test could be promoted to a
   pytest file so the edge-case assertions live next to the code.
5. (Post-demo) Land the codebase slimming plan (`docs/codebase_slimming_plan.md`)
   move queue.
