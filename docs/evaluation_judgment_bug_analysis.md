# Evaluation Judgment Bug Analysis

> Status: analysis only — no production code changed in this step.
> Scope: why some algorithms show `NEAR-SUCCESS` in the Algorithm Comparison
> table even though their Avg Response Time is far worse than the best algorithm.

## 1. Executive Summary

The `JUDGE` column in the Algorithm Comparison table is **not derived from the
metric the user is looking at**. It is read verbatim from a precomputed
`comparison[algo].judgment` string, and:

- In **dashboard_test** that string comes from a **hand-authored static fixture**
  (`dashboard_test/src/data/demoData.js`) whose judgments do **not** follow any
  consistent regret formula. This is the exact source of the observed
  "SJF = 12.40 shown as NEAR-SUCCESS" case.
- In **dashboard_live** that string is produced by the backend
  (`scheduler_simulator.py` or `orchestrator.build_xv6_metrics`) **once**, for a
  **single** metric (Avg Response Time / `target_metric`). The frontend never
  recomputes it, so the moment the Metric dropdown is changed to anything else
  (Avg Waiting Time, Throughput, …) the `JUDGE` column becomes inconsistent with
  the displayed metric.

So the bug is **mixed**: a stale/hand-authored fixture (dashboard_test) on top of
a structural frontend flaw shared by both dashboards (judgment is metric-agnostic
and never recomputed). There is also a **threshold/semantics drift** between the
backend (`SUCCESS < 0.05`, `NEAR < 0.25`, no starvation override) and the
intended standard (`SUCCESS ≤ 0.10`, `NEAR ≤ 0.30`, starvation ⇒ FAIL).

## 2. Observed Problem

Selected metric: **Avg Response Time**. Comparison values (these exactly match
`dashboard_test/src/data/demoData.js`):

| Algo | Avg RT | Shown JUDGE (fixture) | Correct JUDGE (RT regret) |
|------|-------:|-----------------------|---------------------------|
| MLFQ | 1.80 | SUCCESS | SUCCESS |
| RR | 3.20 | NEAR-SUCCESS | **FAIL** |
| SRTF | 4.80 | SUCCESS | **FAIL** |
| Priority | 8.40 | NEAR-SUCCESS | **FAIL** |
| SJF | 12.40 | **NEAR-SUCCESS** | **FAIL** |
| FCFS | 18.40 | FAIL | FAIL |

Best Avg RT = MLFQ = 1.80. SJF = 12.40 ⇒ regret = (12.40 − 1.80) / 1.80 = **5.89**,
which is nowhere near any reasonable NEAR-SUCCESS band. The fixture judgments look
authored "by feel" (good-looking algorithms get SUCCESS/NEAR) rather than computed,
and the frontend trusts them blindly.

## 3. Data Flow

```
                         dashboard_test (UI lab)
                         ───────────────────────
  dashboard_test/src/data/demoData.js   (STATIC, hand-authored)
      └─ export const metrics = { comparison: { <algo>: { judgment, ... } } }
            │  (imported DIRECTLY by the components, ignoring the fixture prop)
            ▼
  AlgorithmComparison.jsx  ──► renders vals['judgment'] verbatim


                         dashboard_live (final demo)
                         ───────────────────────────
  scheduler_simulator.run_all_algorithms()   ── OR ──  orchestrator.build_xv6_metrics()
      └─ computes comparison[algo].judgment ONCE, for avg_response_time / target_metric
            ▼
  outputs/live/metrics.json
            ▼  (orchestrator export step copies the file unchanged)
  dashboard_live/public/live-data/metrics.json
            ▼  (liveDataClient.js polls + parses)
  dashboard_live/src/App.jsx  ──► <AlgorithmComparison metrics=… recommendation=… />
            ▼
  AlgorithmComparison.jsx  ──► renders vals['judgment'] verbatim
```

Key point: in **both** apps the frontend is a pure display of a precomputed
judgment string. No judgment math happens in the frontend.

## 4. Judgment Logic Locations

| # | File / function | Computes judgment? | Metric used | Thresholds | Starvation override |
|---|-----------------|--------------------|-------------|------------|---------------------|
| 1 | `tools/scheduler_simulator.py` → `run_all_algorithms()` (lines ~372–410) | **Yes** — per-algo + overall | Hardcoded `avg_response_time` | `<0.05` SUCCESS, `<0.25` NEAR, else FAIL | No |
| 2 | `scripts/orchestrator.py` → `build_xv6_metrics()` + `_metric_key()` + `_judge()` | **Yes** — per-algo + overall | `target_metric` (metric-aware, correct lower/higher) | `<0.05` SUCCESS, `<0.25` NEAR, else FAIL | No |
| 3 | `tools/metrics.py` → `evaluate_judgment()` | Defined but **NOT called** in `main()` | Hardcoded `avg_response_time` | `<0.05` SUCCESS, `<0.25` NEAR, else FAIL | No |
| 4 | `tools/metrics.py` → `compute()` | No (no judgment/comparison emitted for single trace) | — | — | — |
| 5 | `dashboard_test/src/components/AlgorithmComparison.jsx` | **No** — displays `comparison[algo].judgment` | — | — | — |
| 6 | `dashboard_live/src/components/AlgorithmComparison.jsx` | **No** — displays `comparison[algo].judgment` | — | — | — |
| 7 | `dashboard_*/src/components/MetricVisualization.jsx` | No (only drives the bar chart via local `selKey`) | local dropdown | — | — |
| 8 | `dashboard_test/src/data/demoData.js` | **Precomputed/hand-authored** values, no formula | n/a | n/a | n/a |
| 9 | `tools/schema_compat.py` | No judgment logic (only `algorithm`/`tick` key adapters) | — | — | — |

Note: `EvaluationResult.jsx` (both apps) computes a *recommendation-level* Δ-vs-best
for the single recommended algorithm, but that is separate from the per-row
`JUDGE` column and also assumes lower-is-better only.

## 5. Threshold Comparison

| Aspect | scheduler_simulator.py | orchestrator.build_xv6_metrics | metrics.py (unused) | Frontend | Intended standard |
|--------|------------------------|--------------------------------|---------------------|----------|-------------------|
| SUCCESS | regret < 0.05 | regret < 0.05 | regret < 0.05 | — (display only) | regret ≤ 0.10 |
| NEAR-SUCCESS | regret < 0.25 | regret < 0.25 | regret < 0.25 | — | regret ≤ 0.30 |
| FAIL | otherwise | otherwise | otherwise | — | otherwise |
| Lower-is-better | only avg_response_time | metric-aware (`_metric_key`) | only avg_response_time | — | explicit per-metric |
| Higher-is-better (throughput) | not handled | handled (max best) | not handled | — | required |
| Starvation ⇒ FAIL | not enforced | not enforced | not enforced | not enforced | **required** |
| UNKNOWN (no data) | not modeled | partial | not modeled | shows `—` raw | required |

Observations:
- Backend thresholds are **stricter** than the intended standard (0.05/0.25 vs
  0.10/0.30). They are at least internally consistent between simulator and
  orchestrator, but both disagree with the documented target semantics.
- Only `orchestrator.build_xv6_metrics` is metric-aware; the simulator is locked
  to `avg_response_time`. So the simulator's per-row judgment is already wrong for
  any non-RT target metric.
- No code path forces `FAIL` on starvation.

## 6. Root Cause Hypothesis

Two distinct root causes combine:

**RC-1 (dashboard_test, primary for the observed example): stale / hand-authored
fixture judgment.** `demoData.js` carries `comparison[algo].judgment` strings that
were written by hand and do not match `avg_response_time` regret. The components
(`AlgorithmComparison.jsx`, `MetricVisualization.jsx`, `EvaluationResult.jsx`)
**import `demoData.js` directly** and render the stored judgment verbatim — they
do not even use the currently selected fixture (`App.jsx` only passes `traces` and
`ALGOS` from the fixture; everything else is the static demo object). So the
observed "SJF 12.40 → NEAR-SUCCESS" is a stale data value shown as-is.

**RC-2 (both dashboards, structural): judgment is metric-agnostic and never
recomputed.** `comparison[algo].judgment` is produced once for a single metric
(`avg_response_time`/`target_metric`). The `JUDGE` column always shows that one
value, while the Metric dropdown lives in a *different* component
(`MetricVisualization`, local `selKey` state) and only changes the bar chart. So
even with perfectly correct backend data, selecting "Avg Waiting Time" or
"Throughput" leaves a `JUDGE` column that still reflects Avg Response Time.

Contributing factor: **threshold/semantics drift** (Section 5) — backend uses
0.05/0.25 and no starvation override, diverging from the intended 0.10/0.30 +
starvation⇒FAIL standard, and the simulator hardcodes the metric.

Why dashboard_live currently *looks* fine: the live `metrics.json` happens to be
xv6-generated with `target_metric = avg_response_time`, and `build_xv6_metrics`
computed the per-row judgment against exactly that metric. It is correct only by
coincidence of "selected metric == target metric == avg_response_time". Switch the
dropdown and RC-2 surfaces immediately.

## 7. Correct Expected Calculation

Target metric: `avg_response_time` (lower-is-better). Best = MLFQ = 1.80.

`regret = (algo_value − best_value) / best_value`

| Algo | Value | regret = (v − 1.80) / 1.80 | Intended (≤0.10 / ≤0.30) | Backend (≤0.05 / ≤0.25) |
|------|------:|---------------------------:|--------------------------|--------------------------|
| MLFQ | 1.80 | 0.000 | SUCCESS | SUCCESS |
| RR | 3.20 | 0.778 | FAIL | FAIL |
| SRTF | 4.80 | 1.667 | FAIL | FAIL |
| Priority | 8.40 | 3.667 | FAIL | FAIL |
| SJF | 12.40 | 5.889 | FAIL | FAIL |
| FCFS | 18.40 | 9.222 | FAIL | FAIL |

Under either threshold set, only **MLFQ is SUCCESS** and every other algorithm is
**FAIL**. The fixture's NEAR-SUCCESS (RR, Priority, SJF) and SUCCESS (SRTF) are all
incorrect for this metric.

## 8. Recommended Fix Plan (do NOT implement yet)

1. **Centralize judgment semantics** in one place per layer:
   - Backend: a single helper (e.g. `tools/judgment.py`) with
     `regret(value, best, lower_better)` and `judge(regret, starved)` used by both
     `scheduler_simulator.py` and `orchestrator.build_xv6_metrics`. Replace the
     duplicated 0.05/0.25 blocks. Adopt the standard thresholds (`SUCCESS ≤ 0.10`,
     `NEAR ≤ 0.30`) and `starvation ⇒ FAIL`.
2. **Make the frontend judgment metric-aware.** Add a shared helper, e.g.
   `computeAlgorithmJudgment(algoMetrics, allComparisonMetrics, targetMetric)`
   that:
   - knows lower-is-better vs higher-is-better per metric key,
   - computes best across the comparison for the *selected* metric,
   - returns `FAIL` if `algoMetrics.starvation_occurred`,
   - returns `UNKNOWN` when data is missing.
3. **Lift the selected-metric state up** so the Metric dropdown and the Algorithm
   Comparison table share it (App-level state or context). Recompute the `JUDGE`
   column from the selected metric on every change. Stop rendering raw
   `comparison[algo].judgment` for the row column.
4. **Keep backend `metrics.judgment` for the overall LLM-recommendation verdict**
   (Recommend/Evaluate screens), but treat per-row table judgment as a
   frontend-derived, metric-aware value. Document that the two are different.
5. **Fix the dashboard_test fixture.** Either regenerate `demoData.js` from the
   simulator/orchestrator so judgments are consistent, or remove stored per-row
   judgments from the fixture and rely on the new frontend helper. Also make the
   components honor the selected fixture rather than importing `demoData.js`
   directly (optional, separate cleanup).
6. **Align thresholds** across simulator ↔ orchestrator ↔ (newly used) metrics.py,
   and make the simulator metric-aware (not hardcoded to `avg_response_time`).
7. **Add sanity checks / tests**: a small unit test asserting
   `regret(12.40, 1.80, lower=True) ≈ 5.89 ⇒ FAIL`, plus a fixture lint that
   recomputes stored judgments and flags mismatches.

## 9. Files That Need Changes Later

Frontend (display + recompute):
- `dashboard_test/src/components/AlgorithmComparison.jsx`
- `dashboard_live/src/components/AlgorithmComparison.jsx`
- `dashboard_test/src/components/MetricVisualization.jsx` (lift `selKey` up)
- `dashboard_live/src/components/MetricVisualization.jsx` (lift `selKey` up)
- `dashboard_test/src/App.jsx`, `dashboard_live/src/App.jsx` (shared metric state)
- new: `dashboard_*/src/data/judgment.js` (shared `computeAlgorithmJudgment`)
- `dashboard_test/src/data/demoData.js` (regenerate or strip stale judgments)
- `dashboard_test/src/components/EvaluationResult.jsx` (optional: reuse helper, add higher-is-better + starvation)

Backend (centralize + align):
- `tools/scheduler_simulator.py` (use shared helper, metric-aware, thresholds, starvation)
- `scripts/orchestrator.py` → `build_xv6_metrics` / `_judge` (use shared helper, thresholds, starvation)
- `tools/metrics.py` (either wire `evaluate_judgment` consistently or remove it; align thresholds)
- new (optional): `tools/judgment.py`
- docs: `docs/evaluation_plan.md` (record canonical thresholds + starvation rule)

## 10. Validation Checklist

After the fix is implemented (not now):

1. Regenerate live data:
   - `python3 scripts/orchestrator.py --backend simulator --seed 42 --workload interactive --run-all`
   - (or xv6) `python3 scripts/orchestrator.py --backend xv6 --seed 42 --workload interactive --run-all`
2. Open the dashboard:
   - `cd dashboard_live && npm run dev` (live) and/or `cd dashboard_test && npm run dev` (fixture).
3. Select **Avg Response Time** and confirm the `JUDGE` column matches RT regret:
   - the single best-RT algorithm → SUCCESS; SJF 12.40 (or any algo with regret > 0.30) → **FAIL**.
4. Change the Metric dropdown to **Avg Waiting Time**, then **Throughput**:
   - confirm the `JUDGE` column **recomputes** (best is recomputed for that metric;
     for throughput higher-is-better).
5. Force a starvation case (max_waiting large) and confirm that row shows **FAIL**
   regardless of regret.
6. dashboard_test specifically: confirm the static example no longer shows
   SJF 12.40 as NEAR-SUCCESS.
7. Backend parity: confirm `scheduler_simulator.py` and `orchestrator` produce the
   same judgment for the same `(values, target_metric)` and that thresholds match
   `docs/evaluation_plan.md`.

---

### Appendix — exact code references checked

- `tools/scheduler_simulator.py:372-418` — per-algo + overall judgment, `avg_response_time` hardcoded, thresholds 0.05/0.25.
- `tools/metrics.py:107-119` — `evaluate_judgment` (defined, **unused** in `main`), thresholds 0.05/0.25, `avg_response_time` hardcoded.
- `tools/metrics.py:122-166` — `main()` writes single-trace metrics with **no** judgment/comparison.
- `scripts/orchestrator.py` — `build_xv6_metrics` / `_metric_key` / `_judge`: metric-aware, thresholds 0.05/0.25, no starvation override.
- `dashboard_test/src/components/AlgorithmComparison.jsx:21-24,72-99` — imports `demoData.js`, renders `vals['judgment']` verbatim; `target_metric` only highlights a column.
- `dashboard_test/src/components/MetricVisualization.jsx:14-15` — local `selKey`, drives bar chart only.
- `dashboard_live/src/components/AlgorithmComparison.jsx:21-28,65-81` — same display-only pattern, data via props.
- `dashboard_live/src/components/MetricVisualization.jsx:14-15` — local `selKey`, bar chart only.
- `dashboard_test/src/data/demoData.js` comparison: MLFQ 1.80/SUCCESS, RR 3.20/NEAR-SUCCESS, SRTF 4.80/SUCCESS, Priority 8.40/NEAR-SUCCESS, SJF 12.40/NEAR-SUCCESS, FCFS 18.40/FAIL.
- `dashboard_live/public/live-data/metrics.json` (current, xv6 v7): judgments consistent with `avg_response_time` only because target == selected == RT.

---
---

# 평가 판정(Judgment) 버그 분석 (한국어)

> 상태: 분석 전용 — 이 단계에서 프로덕션 코드는 수정하지 않음.
> 범위: Algorithm Comparison 표에서 일부 알고리즘이 Avg Response Time이 최고
> 알고리즘보다 훨씬 나쁜데도 `NEAR-SUCCESS`로 표시되는 이유.

## 1. 요약 (Executive Summary)

Algorithm Comparison 표의 `JUDGE` 열은 **사용자가 보고 있는 메트릭으로부터 도출되지
않습니다.** 미리 계산된 `comparison[algo].judgment` 문자열을 그대로 읽어 표시하며:

- **dashboard_test**에서는 이 문자열이 **손으로 작성된 정적 fixture**
  (`dashboard_test/src/data/demoData.js`)에서 오며, 그 judgment 값들은 일관된 regret
  공식을 전혀 따르지 않습니다. 이것이 관찰된 "SJF = 12.40인데 NEAR-SUCCESS"의 직접
  원인입니다.
- **dashboard_live**에서는 이 문자열이 백엔드
  (`scheduler_simulator.py` 또는 `orchestrator.build_xv6_metrics`)에서 **단일**
  메트릭(Avg Response Time / `target_metric`) 기준으로 **한 번만** 생성됩니다.
  프론트엔드는 절대 재계산하지 않으므로, Metric 드롭다운을 다른 값(Avg Waiting Time,
  Throughput 등)으로 바꾸는 순간 `JUDGE` 열은 표시 중인 메트릭과 어긋납니다.

따라서 버그는 **혼합(mixed)**입니다: stale/손작성 fixture(dashboard_test) 위에, 두
대시보드가 공유하는 구조적 결함(judgment이 메트릭 비인식이며 재계산되지 않음)이 겹쳐
있습니다. 또한 백엔드(`SUCCESS < 0.05`, `NEAR < 0.25`, starvation 미반영)와 의도된
표준(`SUCCESS ≤ 0.10`, `NEAR ≤ 0.30`, starvation ⇒ FAIL) 사이의 **임계값/의미 드리프트**도
존재합니다.

## 2. 관찰된 문제 (Observed Problem)

선택 메트릭: **Avg Response Time**. 비교 값(아래는 `dashboard_test/src/data/demoData.js`와
정확히 일치):

| Algo | Avg RT | 표시된 JUDGE (fixture) | 올바른 JUDGE (RT regret) |
|------|-------:|------------------------|--------------------------|
| MLFQ | 1.80 | SUCCESS | SUCCESS |
| RR | 3.20 | NEAR-SUCCESS | **FAIL** |
| SRTF | 4.80 | SUCCESS | **FAIL** |
| Priority | 8.40 | NEAR-SUCCESS | **FAIL** |
| SJF | 12.40 | **NEAR-SUCCESS** | **FAIL** |
| FCFS | 18.40 | FAIL | FAIL |

최고 Avg RT = MLFQ = 1.80. SJF = 12.40 ⇒ regret = (12.40 − 1.80) / 1.80 = **5.89**로,
어떤 합리적인 NEAR-SUCCESS 구간에도 근처에 가지 않습니다. fixture의 judgment는 계산된
값이 아니라 "감으로" 작성된 것처럼 보이며(좋아 보이는 알고리즘에 SUCCESS/NEAR 부여),
프론트엔드는 이를 무비판적으로 신뢰합니다.

## 3. 데이터 흐름 (Data Flow)

```
                         dashboard_test (UI lab)
                         ───────────────────────
  dashboard_test/src/data/demoData.js   (정적, 손작성)
      └─ export const metrics = { comparison: { <algo>: { judgment, ... } } }
            │  (fixture prop을 무시하고 컴포넌트가 직접 import)
            ▼
  AlgorithmComparison.jsx  ──► vals['judgment']를 그대로 렌더링


                         dashboard_live (최종 데모)
                         ───────────────────────────
  scheduler_simulator.run_all_algorithms()   ── 또는 ──  orchestrator.build_xv6_metrics()
      └─ comparison[algo].judgment를 avg_response_time / target_metric 기준 1회 계산
            ▼
  outputs/live/metrics.json
            ▼  (orchestrator export 단계에서 파일 그대로 복사)
  dashboard_live/public/live-data/metrics.json
            ▼  (liveDataClient.js 폴링 + 파싱)
  dashboard_live/src/App.jsx  ──► <AlgorithmComparison metrics=… recommendation=… />
            ▼
  AlgorithmComparison.jsx  ──► vals['judgment']를 그대로 렌더링
```

핵심: **두 앱 모두** 프론트엔드는 미리 계산된 judgment 문자열을 단순 표시할 뿐입니다.
프론트엔드에서 judgment 계산은 일어나지 않습니다.

## 4. 판정 로직 위치 (Judgment Logic Locations)

| # | 파일 / 함수 | judgment 계산? | 사용 메트릭 | 임계값 | starvation override |
|---|-------------|----------------|-------------|--------|---------------------|
| 1 | `tools/scheduler_simulator.py` → `run_all_algorithms()` (약 372–410행) | **예** — per-algo + 전체 | `avg_response_time` 하드코딩 | `<0.05` SUCCESS, `<0.25` NEAR, 그 외 FAIL | 없음 |
| 2 | `scripts/orchestrator.py` → `build_xv6_metrics()` + `_metric_key()` + `_judge()` | **예** — per-algo + 전체 | `target_metric` (메트릭 인식, lower/higher 정확) | `<0.05` SUCCESS, `<0.25` NEAR, 그 외 FAIL | 없음 |
| 3 | `tools/metrics.py` → `evaluate_judgment()` | 정의돼 있으나 `main()`에서 **호출 안 됨** | `avg_response_time` 하드코딩 | `<0.05` SUCCESS, `<0.25` NEAR, 그 외 FAIL | 없음 |
| 4 | `tools/metrics.py` → `compute()` | 아니오 (단일 트레이스에 judgment/comparison 미출력) | — | — | — |
| 5 | `dashboard_test/src/components/AlgorithmComparison.jsx` | **아니오** — `comparison[algo].judgment` 표시 | — | — | — |
| 6 | `dashboard_live/src/components/AlgorithmComparison.jsx` | **아니오** — `comparison[algo].judgment` 표시 | — | — | — |
| 7 | `dashboard_*/src/components/MetricVisualization.jsx` | 아니오 (로컬 `selKey`로 막대 차트만 구동) | 로컬 드롭다운 | — | — |
| 8 | `dashboard_test/src/data/demoData.js` | **미리 계산/손작성** 값, 공식 없음 | 해당 없음 | 해당 없음 | 해당 없음 |
| 9 | `tools/schema_compat.py` | judgment 로직 없음 (`algorithm`/`tick` 키 어댑터만) | — | — | — |

참고: `EvaluationResult.jsx`(두 앱)는 추천 알고리즘 1개에 대한 *추천 수준* Δ-vs-best를
계산하지만, 이는 per-row `JUDGE` 열과 별개이며 lower-is-better만 가정합니다.

## 5. 임계값 비교 (Threshold Comparison)

| 항목 | scheduler_simulator.py | orchestrator.build_xv6_metrics | metrics.py (미사용) | 프론트엔드 | 의도된 표준 |
|------|------------------------|--------------------------------|---------------------|-----------|-------------|
| SUCCESS | regret < 0.05 | regret < 0.05 | regret < 0.05 | — (표시만) | regret ≤ 0.10 |
| NEAR-SUCCESS | regret < 0.25 | regret < 0.25 | regret < 0.25 | — | regret ≤ 0.30 |
| FAIL | 그 외 | 그 외 | 그 외 | — | 그 외 |
| Lower-is-better | avg_response_time만 | 메트릭 인식 (`_metric_key`) | avg_response_time만 | — | 메트릭별 명시 |
| Higher-is-better (throughput) | 미처리 | 처리 (max가 best) | 미처리 | — | 필요 |
| Starvation ⇒ FAIL | 미적용 | 미적용 | 미적용 | 미적용 | **필요** |
| UNKNOWN (데이터 없음) | 미모델링 | 부분 | 미모델링 | 원시값 `—` 표시 | 필요 |

관찰:
- 백엔드 임계값이 의도된 표준보다 **더 엄격**(0.05/0.25 vs 0.10/0.30). simulator와
  orchestrator 사이에서는 최소한 내부적으로 일관되지만, 둘 다 문서화된 목표 의미와 다릅니다.
- `orchestrator.build_xv6_metrics`만 메트릭 인식이고, simulator는 `avg_response_time`에
  고정. 따라서 simulator의 per-row judgment는 RT가 아닌 target 메트릭에서 이미 틀립니다.
- starvation 시 `FAIL`을 강제하는 코드 경로가 없습니다.

## 6. 근본 원인 가설 (Root Cause Hypothesis)

두 개의 별개 근본 원인이 결합:

**RC-1 (dashboard_test, 관찰 예시의 주원인): stale / 손작성 fixture judgment.**
`demoData.js`가 `avg_response_time` regret과 맞지 않는 손작성 `comparison[algo].judgment`
문자열을 담고 있습니다. 컴포넌트(`AlgorithmComparison.jsx`, `MetricVisualization.jsx`,
`EvaluationResult.jsx`)는 **`demoData.js`를 직접 import**하여 저장된 judgment를 그대로
렌더링합니다 — 심지어 현재 선택된 fixture를 사용하지도 않습니다(`App.jsx`는 fixture에서
`traces`와 `ALGOS`만 전달하고 나머지는 정적 demo 객체). 그래서 관찰된 "SJF 12.40 →
NEAR-SUCCESS"는 stale 데이터 값이 그대로 표시된 것입니다.

**RC-2 (두 대시보드, 구조적): judgment이 메트릭 비인식이고 재계산되지 않음.**
`comparison[algo].judgment`는 단일 메트릭(`avg_response_time`/`target_metric`)으로 한 번
생성됩니다. `JUDGE` 열은 항상 그 한 값을 표시하는 반면, Metric 드롭다운은 *다른* 컴포넌트
(`MetricVisualization`, 로컬 `selKey` 상태)에 있고 막대 차트만 바꿉니다. 따라서 백엔드
데이터가 완벽히 정확하더라도 "Avg Waiting Time"이나 "Throughput"을 선택하면 `JUDGE` 열은
여전히 Avg Response Time을 반영합니다.

기여 요인: **임계값/의미 드리프트**(5절) — 백엔드는 0.05/0.25에 starvation override가 없어
의도된 0.10/0.30 + starvation⇒FAIL 표준과 어긋나고, simulator는 메트릭을 하드코딩합니다.

dashboard_live가 현재 *정상으로 보이는* 이유: live `metrics.json`이 마침 xv6 생성이고
`target_metric = avg_response_time`이며, `build_xv6_metrics`가 정확히 그 메트릭으로 per-row
judgment를 계산했기 때문입니다. "선택 메트릭 == target 메트릭 == avg_response_time"이
우연히 일치할 때만 맞습니다. 드롭다운을 바꾸면 RC-2가 즉시 드러납니다.

## 7. 올바른 기대 계산 (Correct Expected Calculation)

target 메트릭: `avg_response_time` (낮을수록 좋음). best = MLFQ = 1.80.

`regret = (algo_value − best_value) / best_value`

| Algo | 값 | regret = (v − 1.80) / 1.80 | 의도 표준 (≤0.10 / ≤0.30) | 백엔드 (≤0.05 / ≤0.25) |
|------|---:|---------------------------:|---------------------------|------------------------|
| MLFQ | 1.80 | 0.000 | SUCCESS | SUCCESS |
| RR | 3.20 | 0.778 | FAIL | FAIL |
| SRTF | 4.80 | 1.667 | FAIL | FAIL |
| Priority | 8.40 | 3.667 | FAIL | FAIL |
| SJF | 12.40 | 5.889 | FAIL | FAIL |
| FCFS | 18.40 | 9.222 | FAIL | FAIL |

두 임계값 세트 어느 쪽에서도 **MLFQ만 SUCCESS**, 나머지는 모두 **FAIL**입니다. fixture의
NEAR-SUCCESS(RR, Priority, SJF)와 SUCCESS(SRTF)는 이 메트릭에서 모두 틀렸습니다.

## 8. 권장 수정 계획 (아직 구현하지 말 것)

1. **판정 의미를 한 곳으로 중앙화** (레이어별 단일 위치):
   - 백엔드: 공통 헬퍼(예: `tools/judgment.py`)에 `regret(value, best, lower_better)`,
     `judge(regret, starved)`를 두고 `scheduler_simulator.py`와
     `orchestrator.build_xv6_metrics`가 함께 사용. 중복된 0.05/0.25 블록 제거. 표준 임계값
     (`SUCCESS ≤ 0.10`, `NEAR ≤ 0.30`)과 `starvation ⇒ FAIL` 채택.
2. **프론트엔드 judgment을 메트릭 인식으로.** 공통 헬퍼
   `computeAlgorithmJudgment(algoMetrics, allComparisonMetrics, targetMetric)` 추가:
   - 메트릭 키별 lower-is-better / higher-is-better 인지,
   - *선택된* 메트릭으로 comparison 전체의 best 계산,
   - `algoMetrics.starvation_occurred`면 `FAIL` 반환,
   - 데이터 부족 시 `UNKNOWN` 반환.
3. **선택 메트릭 상태를 상위로 끌어올리기**(lift state up). Metric 드롭다운과 Algorithm
   Comparison 표가 같은 상태(App 레벨 state 또는 context)를 공유하게 하고, 변경 시마다
   선택 메트릭으로 `JUDGE` 열을 재계산. row 열에서 원시 `comparison[algo].judgment` 표시
   중단.
4. **백엔드 `metrics.judgment`는 전체 LLM 추천 판정용으로 유지**(Recommend/Evaluate 화면)
   하되, per-row 표 judgment는 프론트엔드에서 도출하는 메트릭 인식 값으로 취급. 둘이 다른
   값임을 문서화.
5. **dashboard_test fixture 수정.** `demoData.js`를 simulator/orchestrator로 재생성해
   judgment를 일관되게 하거나, fixture에서 저장된 per-row judgment를 제거하고 새 프론트엔드
   헬퍼에 의존. 컴포넌트가 `demoData.js`를 직접 import하지 말고 선택된 fixture를 따르도록
   하는 것도(선택적 정리) 권장.
6. **임계값 정렬**: simulator ↔ orchestrator ↔ (새로 사용할) metrics.py 간 일치, simulator를
   메트릭 인식으로(avg_response_time 하드코딩 제거).
7. **검증/테스트 추가**: `regret(12.40, 1.80, lower=True) ≈ 5.89 ⇒ FAIL`을 단언하는 단위
   테스트 + 저장된 judgment를 재계산해 불일치를 잡는 fixture lint.

## 9. 이후 변경이 필요한 파일

프론트엔드(표시 + 재계산):
- `dashboard_test/src/components/AlgorithmComparison.jsx`
- `dashboard_live/src/components/AlgorithmComparison.jsx`
- `dashboard_test/src/components/MetricVisualization.jsx` (`selKey` 상위로)
- `dashboard_live/src/components/MetricVisualization.jsx` (`selKey` 상위로)
- `dashboard_test/src/App.jsx`, `dashboard_live/src/App.jsx` (공유 메트릭 상태)
- 신규: `dashboard_*/src/data/judgment.js` (공통 `computeAlgorithmJudgment`)
- `dashboard_test/src/data/demoData.js` (재생성 또는 stale judgment 제거)
- `dashboard_test/src/components/EvaluationResult.jsx` (선택: 헬퍼 재사용, higher-is-better + starvation 추가)

백엔드(중앙화 + 정렬):
- `tools/scheduler_simulator.py` (공통 헬퍼 사용, 메트릭 인식, 임계값, starvation)
- `scripts/orchestrator.py` → `build_xv6_metrics` / `_judge` (공통 헬퍼, 임계값, starvation)
- `tools/metrics.py` (`evaluate_judgment`을 일관되게 연결하거나 제거; 임계값 정렬)
- 신규(선택): `tools/judgment.py`
- 문서: `docs/evaluation_plan.md` (정식 임계값 + starvation 규칙 기록)

## 10. 검증 체크리스트

수정 구현 후(지금은 아님):

1. live 데이터 재생성:
   - `python3 scripts/orchestrator.py --backend simulator --seed 42 --workload interactive --run-all`
   - (또는 xv6) `python3 scripts/orchestrator.py --backend xv6 --seed 42 --workload interactive --run-all`
2. 대시보드 열기:
   - `cd dashboard_live && npm run dev` (live) 및/또는 `cd dashboard_test && npm run dev` (fixture).
3. **Avg Response Time** 선택 후 `JUDGE` 열이 RT regret과 일치하는지 확인:
   - 최고 RT 알고리즘 → SUCCESS; SJF 12.40(또는 regret > 0.30인 알고리즘) → **FAIL**.
4. Metric 드롭다운을 **Avg Waiting Time**, 그다음 **Throughput**으로 변경:
   - `JUDGE` 열이 **재계산**되는지 확인(해당 메트릭으로 best 재계산; throughput은 높을수록 좋음).
5. starvation 케이스(max_waiting 큰 값)를 만들어 해당 행이 regret과 무관하게 **FAIL**인지 확인.
6. dashboard_test 한정: 정적 예시에서 SJF 12.40이 더 이상 NEAR-SUCCESS로 표시되지 않는지 확인.
7. 백엔드 동등성: `scheduler_simulator.py`와 `orchestrator`가 동일 `(values, target_metric)`에
   대해 동일 judgment를 내고, 임계값이 `docs/evaluation_plan.md`와 일치하는지 확인.

---

### 부록 — 확인한 정확한 코드 위치

- `tools/scheduler_simulator.py:372-418` — per-algo + 전체 judgment, `avg_response_time` 하드코딩, 임계값 0.05/0.25.
- `tools/metrics.py:107-119` — `evaluate_judgment` (정의됨, `main`에서 **미사용**), 임계값 0.05/0.25, `avg_response_time` 하드코딩.
- `tools/metrics.py:122-166` — `main()`은 단일 트레이스 메트릭만 쓰고 judgment/comparison **없음**.
- `scripts/orchestrator.py` — `build_xv6_metrics` / `_metric_key` / `_judge`: 메트릭 인식, 임계값 0.05/0.25, starvation override 없음.
- `dashboard_test/src/components/AlgorithmComparison.jsx:21-24,72-99` — `demoData.js` import, `vals['judgment']` 그대로 렌더; `target_metric`은 열 강조에만 사용.
- `dashboard_test/src/components/MetricVisualization.jsx:14-15` — 로컬 `selKey`, 막대 차트만 구동.
- `dashboard_live/src/components/AlgorithmComparison.jsx:21-28,65-81` — 동일한 표시 전용 패턴, 데이터는 props.
- `dashboard_live/src/components/MetricVisualization.jsx:14-15` — 로컬 `selKey`, 막대 차트만 구동.
- `dashboard_test/src/data/demoData.js` comparison: MLFQ 1.80/SUCCESS, RR 3.20/NEAR-SUCCESS, SRTF 4.80/SUCCESS, Priority 8.40/NEAR-SUCCESS, SJF 12.40/NEAR-SUCCESS, FCFS 18.40/FAIL.
- `dashboard_live/public/live-data/metrics.json` (현재, xv6 v7): target == selected == RT이기 때문에만 `avg_response_time`과 일관됨.
