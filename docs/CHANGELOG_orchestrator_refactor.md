# Change Log — Orchestrator Refactor & Dashboard Polish

> Branch: `feature/live-dashboard-split` · Date: 2026-05-25 · Status: **uncommitted**
> 분량: 2개 작업 묶음 — (1) 대시보드 UI 다듬기, (2) Orchestrator 아키텍처 리팩터 (기반 단계)

---

# English

## Overview
Two bodies of work are currently uncommitted on this branch:

1. **dashboard_test UI polish** — filled empty space in the 3-step (Recommend / Execute / Evaluate) test dashboard.
2. **Orchestrator architecture refactor (foundation phases)** — make the host-side Orchestrator the control plane, fix the trace parser to match real xv6 output, add schema-compatibility adapters, and make `dashboard_live` clearly show whether data came from real xv6 or the Python simulator. The risky xv6/QEMU phases are intentionally **deferred**.

## 1. dashboard_test UI polish
- `dashboard_test/src/components/LLMRecommendation.jsx` + `App.css` — rebuilt the Recommend screen's dominant card: large algorithm hero, parameter grid, reasoning, and a **"Considered Alternatives" ranking** driven by real `metrics.comparison` data (justifies why the chosen algorithm wins on the target metric), plus a workload/risk footer.
- `dashboard_test/src/App.jsx` (`ExecuteInfoCard`) + `App.css` — filled the "Running Now" card with live stats: completion progress bar, per-state counts (Running/Ready/Waiting/Done), preemption count.
- `dashboard_test/src/App.css` — turned Process Lanes into a full-height swimlane chart (removed the `max-height: 24px` cap; continuous grid lines + "now" marker across all lanes).
- `dashboard_test/src/components/EvaluationResult.jsx` + `App.css` — filled the verdict card's empty middle with a **per-process metrics table** from `metrics.per_process` (PID / Arrival / Response / Wait / Turnaround).
- `dashboard_test/src/components/Header.jsx`, `LLMExplanation.jsx`, `ProcessState.jsx` — supporting changes for the 3-step layout (step nav, compact explanation mode, state diagram).

## 2. Orchestrator architecture refactor (foundation)

### New files
| File | Purpose |
|------|---------|
| `tools/schema_compat.py` | Backward-compatible readers: `get_recommended_algorithm`, `get_guard_algorithm`, `get_event_tick`, `get_event_algo`, `get_backend`, `normalize_algo`. Tolerates `algorithm` vs `recommended_scheduling_algorithm` vs `scheduling_algorithm`, `tick` vs `time`, `algo` vs `algorithm`. |
| `dashboard_live/src/data/schemaCompat.js` | JavaScript mirror of the same adapters for the React app. |
| `scripts/orchestrator.py` | Host-side control plane (renamed from `run_live_dashboard_pipeline.py` via `git mv`, history preserved). |
| `scripts/run_live_dashboard_pipeline.py` | Thin deprecation shim that forwards to `orchestrator.py`. |
| `docs/implementation_status.md` | Honest Feature / Status / Evidence / Run Command / Risk table. |
| `docs/orchestrator_design.md` | Why the Orchestrator exists; why `schedtest.c` can't call the LLM; why the simulator is not the final backend; sequential same-seed fairness rule. |

### Modified files
| File | Change |
|------|--------|
| `tools/trace_parser.py` | Rewrote parsing to match the **real** kernel format `[SCHED] tick=.. algo=.. event=.. pid=..` and user format `[SCHEDTEST] event=.. key=value`. Generic `key=value` tokenizer (order-independent), `--out-dir`/`--seed`/`--profile` options, parse-error counting, never crashes on unknown lines, normalized JSONL with `source="xv6"`. (Previously its regex matched neither — it parsed zero real events.) |
| `tools/scheduler_simulator.py` | Reads the guard algorithm via `schema_compat.get_guard_algorithm` so it works whether the guard file uses `algorithm` or `scheduling_algorithm` (previously it silently defaulted to MLFQ). Role downgraded to dev/fallback in docs. |
| `scripts/orchestrator.py` | New CLI `--backend {xv6,simulator} --seed N --workload PROFILE --run-all [--algo NAME]`. Steps: profile→workload file, workload_analyzer, llm_advisor (demo fallback if no API key), algorithm_guard, **LLM-selected algorithm first** then the rest, run backend, export to `dashboard_live/public/live-data/` with an enriched manifest. Simulator backend works end-to-end; **xv6 backend is a clean stub** (CLI accepts it but errors with "use --backend simulator for now"). |
| `dashboard_live/src/components/Header.jsx`, `App.jsx`, `App.css` | Added a prominent backend badge — green **"Backend: XV6 TRACE"** vs amber **"Backend: SIMULATOR FALLBACK"** (with warning text), plus a meta strip (workload, LLM-selected algo, algorithm count, seed, total event count). No layout rewrite. |
| `README.md` | Orchestrator-centric architecture, role clarifications (Orchestrator / schedtest / simulator-as-fallback), run commands for both backends, implementation-status summary. |
| `docs/demo_runbook.md`, `docs/trace_format.md`, `docs/dashboard_data_contract.md` | Updated demo flow, documented real `[SCHED]`/`[SCHEDTEST]` formats + parser fields, fixed a stale "produced by" line. |
| `dashboard_live/public/live-data/*`, `outputs/workload_summary.json` | Regenerated data from an orchestrator simulator run (new manifest schema, refreshed traces/metrics). |

### Enriched manifest schema
`dashboard_live/public/live-data/manifest.json` now carries `backend`, `seed`, `workload_type`, `llm_selected_algorithm`, `algorithms_executed`, `generated_at`, `orchestrator_version` — plus the legacy mirror fields (`mode`, `version`, `workload`, `algorithms`, `recommended_algorithm`, `target_metric`, `updated_at`) so the existing dashboard polling keeps working.

### Validation run (all passing)
- `python3 -m py_compile tools/*.py scripts/*.py` — OK
- `python3 scripts/orchestrator.py --backend simulator --seed 42 --workload interactive --run-all` — full pipeline, manifest v5, 6 traces (1353 events)
- `python3 scripts/orchestrator.py --backend xv6 ...` — exits cleanly (code 1) with a helpful message
- `cd dashboard_live && npm run build` — OK; backend badge verified visually
- `trace_parser` parses real `[SCHED]`/`[SCHEDTEST]` lines and ignores boot spam

### Deferred (intentionally, pending review)
- `schedtest.c` → `schedtest <algorithm> <seed> <profile>` with deterministic workload + `[SCHEDTEST]` logs.
- Kernel trace richness in `proc.c`/`trap.c` (drop the 1-in-5 throttle; add PREEMPT / EXIT / QUEUE_CHANGE).
- QEMU automation in `orchestrator.run_xv6_backend()` + multi-trace metrics aggregation for the xv6 path.
- Runtime correction loop remains **Partial / Future Work** (only event detection exists).

---

# 한글

## 개요
현재 브랜치에 커밋되지 않은 작업은 두 묶음입니다.

1. **dashboard_test UI 다듬기** — 3단계(Recommend / Execute / Evaluate) 테스트 대시보드의 빈 공간을 채움.
2. **Orchestrator 아키텍처 리팩터 (기반 단계)** — 호스트 측 Orchestrator를 제어 평면으로 승격하고, 트레이스 파서를 실제 xv6 출력 형식에 맞게 고치고, 스키마 호환 어댑터를 추가하고, `dashboard_live`가 데이터 출처(실제 xv6 vs Python 시뮬레이터)를 명확히 표시하도록 함. 위험도가 높은 xv6/QEMU 단계는 의도적으로 **보류**.

## 1. dashboard_test UI 다듬기
- `dashboard_test/src/components/LLMRecommendation.jsx` + `App.css` — Recommend 화면의 중심 카드를 재구성: 큰 알고리즘 히어로, 파라미터 그리드, 추론(reasoning), 그리고 실제 `metrics.comparison` 데이터 기반의 **"Considered Alternatives" 랭킹**(선택된 알고리즘이 target metric에서 왜 우수한지 시각적으로 정당화) + 워크로드/리스크 footer.
- `dashboard_test/src/App.jsx`(`ExecuteInfoCard`) + `App.css` — "Running Now" 카드를 라이브 통계로 채움: 완료 진행률 바, 상태별 카운트(Running/Ready/Waiting/Done), 선점(preemption) 수.
- `dashboard_test/src/App.css` — Process Lanes를 전체 높이 스윔레인 차트로 변경(`max-height: 24px` 캡 제거; 전 레인을 관통하는 연속 그리드선과 "now" 마커).
- `dashboard_test/src/components/EvaluationResult.jsx` + `App.css` — 판정 카드의 빈 가운데에 `metrics.per_process` 기반 **프로세스별 메트릭 테이블**(PID / Arrival / Response / Wait / Turnaround) 추가.
- `dashboard_test/src/components/Header.jsx`, `LLMExplanation.jsx`, `ProcessState.jsx` — 3단계 레이아웃 관련 보조 변경(단계 내비게이션, compact 설명 모드, 상태 다이어그램).

## 2. Orchestrator 아키텍처 리팩터 (기반)

### 신규 파일
| 파일 | 목적 |
|------|------|
| `tools/schema_compat.py` | 하위 호환 리더: `get_recommended_algorithm`, `get_guard_algorithm`, `get_event_tick`, `get_event_algo`, `get_backend`, `normalize_algo`. `algorithm` vs `recommended_scheduling_algorithm` vs `scheduling_algorithm`, `tick` vs `time`, `algo` vs `algorithm` 차이를 모두 흡수. |
| `dashboard_live/src/data/schemaCompat.js` | React 앱용 동일 어댑터의 JavaScript 버전. |
| `scripts/orchestrator.py` | 호스트 측 제어 평면(`run_live_dashboard_pipeline.py`를 `git mv`로 이름 변경, 이력 보존). |
| `scripts/run_live_dashboard_pipeline.py` | `orchestrator.py`로 포워딩하는 얇은 deprecation shim. |
| `docs/implementation_status.md` | 솔직한 기능/상태/근거/실행명령/리스크 표. |
| `docs/orchestrator_design.md` | Orchestrator가 필요한 이유; `schedtest.c`가 LLM을 호출할 수 없는 이유; 시뮬레이터가 최종 백엔드가 아닌 이유; 동일 seed 순차 실행 공정성 규칙. |

### 수정 파일
| 파일 | 변경 내용 |
|------|----------|
| `tools/trace_parser.py` | 실제 커널 형식 `[SCHED] tick=.. algo=.. event=.. pid=..` 와 유저 형식 `[SCHEDTEST] event=.. key=value` 에 맞게 파싱 재작성. 순서 무관 `key=value` 토크나이저, `--out-dir`/`--seed`/`--profile` 옵션, 파싱 오류 카운트, 알 수 없는 줄에도 안 죽음, `source="xv6"` 포함 정규화 JSONL. (기존 정규식은 둘 다 매칭하지 못해 실제 이벤트를 0개 파싱했음.) |
| `tools/scheduler_simulator.py` | `schema_compat.get_guard_algorithm`으로 guard 알고리즘을 읽어 guard 파일이 `algorithm`이든 `scheduling_algorithm`이든 동작(이전엔 조용히 MLFQ로 기본값 처리됨). 문서상 역할을 개발/폴백으로 강등. |
| `scripts/orchestrator.py` | 신규 CLI `--backend {xv6,simulator} --seed N --workload PROFILE --run-all [--algo NAME]`. 단계: profile→워크로드 파일, workload_analyzer, llm_advisor(키 없으면 데모 폴백), algorithm_guard, **LLM이 선택한 알고리즘 먼저** 그 다음 나머지, 백엔드 실행, 강화된 manifest와 함께 `dashboard_live/public/live-data/`로 export. 시뮬레이터 백엔드는 end-to-end 동작; **xv6 백엔드는 깔끔한 stub**(CLI는 받지만 "지금은 --backend simulator를 쓰라"는 메시지와 함께 종료). |
| `dashboard_live/src/components/Header.jsx`, `App.jsx`, `App.css` | 눈에 띄는 백엔드 배지 추가 — 초록 **"Backend: XV6 TRACE"** vs 노랑(amber) **"Backend: SIMULATOR FALLBACK"**(경고 문구 포함), 그리고 메타 스트립(workload, LLM 선택 알고리즘, 알고리즘 수, seed, 총 이벤트 수). 레이아웃 재작성 없음. |
| `README.md` | Orchestrator 중심 아키텍처, 역할 정리(Orchestrator / schedtest / 폴백 시뮬레이터), 두 백엔드 실행 명령, 구현 현황 요약. |
| `docs/demo_runbook.md`, `docs/trace_format.md`, `docs/dashboard_data_contract.md` | 데모 흐름 갱신, 실제 `[SCHED]`/`[SCHEDTEST]` 형식과 파서 필드 문서화, 오래된 "produced by" 문구 수정. |
| `dashboard_live/public/live-data/*`, `outputs/workload_summary.json` | Orchestrator 시뮬레이터 실행으로 데이터 재생성(새 manifest 스키마, 트레이스/메트릭 갱신). |

### 강화된 manifest 스키마
`dashboard_live/public/live-data/manifest.json`에 `backend`, `seed`, `workload_type`, `llm_selected_algorithm`, `algorithms_executed`, `generated_at`, `orchestrator_version` 추가 — 기존 대시보드 폴링이 계속 동작하도록 레거시 미러 필드(`mode`, `version`, `workload`, `algorithms`, `recommended_algorithm`, `target_metric`, `updated_at`)도 유지.

### 검증 실행 (모두 통과)
- `python3 -m py_compile tools/*.py scripts/*.py` — OK
- `python3 scripts/orchestrator.py --backend simulator --seed 42 --workload interactive --run-all` — 전체 파이프라인, manifest v5, 트레이스 6개(이벤트 1353개)
- `python3 scripts/orchestrator.py --backend xv6 ...` — 안내 메시지와 함께 정상 종료(코드 1)
- `cd dashboard_live && npm run build` — OK; 백엔드 배지 시각 확인
- `trace_parser` 가 실제 `[SCHED]`/`[SCHEDTEST]` 줄을 파싱하고 부팅 로그는 무시

### 보류 (의도적, 검토 후 진행)
- `schedtest.c` → `schedtest <algorithm> <seed> <profile>` (결정적 워크로드 + `[SCHEDTEST]` 로그).
- `proc.c`/`trap.c` 커널 트레이스 강화(5회당 1회 throttle 제거; PREEMPT / EXIT / QUEUE_CHANGE 추가).
- `orchestrator.run_xv6_backend()`의 QEMU 자동화 + xv6 경로용 다중 트레이스 메트릭 집계.
- 런타임 보정 루프는 **Partial / Future Work** 유지(이벤트 감지만 존재).
