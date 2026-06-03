# Visual Scheduler Project Progress Report

> 프로젝트명: **Visual Scheduler** (repository 내부 코드 베이스명: *LLM Sched Copilot*)  
> 테마: **LLM-Assisted xv6 Scheduling Algorithm Lab** (Direction B — LLM for OS)  
> LLM 백엔드: **Upstage Solar Pro 3** (`tools/solar_client.py`)  
> 보고서 작성일: **2026-05-28**  (branch: `feat/upstage-runtime-strict`, base: `main`)  
> 본 보고서는 코드/git history를 직접 분석한 결과만 기록한다. 추측·과장 금지.

---

## 1. Executive Summary

이 프로젝트는 **xv6 (RISC-V)** 의 CPU scheduler를 LLM이 “추천·해설·교정”하는 **LLM-for-OS** 교육 시스템이다. LLM(Upstage Solar Pro 3)이 워크로드 요약(JSON)을 읽어 **Scheduling Algorithm** 을 추천하면(`tools/llm_advisor.py`), `tools/algorithm_guard.py` 가 알고리즘·파라미터·메트릭 적합도를 검증한 뒤(`guard_decision.json`), `scripts/orchestrator.py` 가 호스트 제어 평면 역할로 두 가지 백엔드(① 실제 xv6 + QEMU의 `schedtest`, ② 호스트 측 Python `scheduler_simulator.py`) 중 하나를 실행한다. 실행 결과로 나온 `[SCHED]` / `[SCHEDTEST]` trace는 `tools/trace_parser.py` 가 정규화하고, `tools/metrics.py` 가 응답 시간(response time), 대기 시간(waiting time), 반환 시간(turnaround time), throughput, starvation, regret_score, judgment(SUCCESS / NEAR-SUCCESS / FAIL)를 산출하고, `tools/trace_explainer.py` 가 다시 Solar Pro 3 로 자연어 해설(`trace_explanation.json`)을 만든다. `dashboard_live` (React/Vite, primary)와 `dashboard_test` (UI lab)이 이 JSON/JSONL 들을 시각화한다.

**현재 진척:** end-to-end pipeline은 **시뮬레이터 백엔드 기준 완전 동작**, **xv6+QEMU 백엔드도 `schedtest` + orchestrator로 실행 가능**(RR/FCFS/PRIORITY/MLFQ/SJF/SRTF 6개 알고리즘이 `kernel/proc.c` 와 `user/schedtest.c` 에 모두 구현). 4개 curated profile(interactive / cpu_bound / mixed / priority_sensitive)에 대한 **xv6 snapshot 4세트**가 `dashboard_live/public/live-data/snapshots/` 에 출판되어 있고 dashboard의 snapshot selector로 전환 가능. GitHub Actions CI(QEMU 없는 lightweight smoke + `--preview` validator + `--snapshots` 모드)도 들어와 있다. **closed-loop runtime correction**은 `event_detector → correction_proposer → correction_guard` 의 **preview-only 경로까지만 구현**되어 있으며, LLM 호출 → xv6 apply → `CORRECTION_APPLIED` trace event 는 **Future Work**.

### 표 1.1 — Overall Progress Snapshot

| Area | Status | Evidence | Notes |
|---|---|---|---|
| Project direction / README | DONE | `README.md` (29 KB, 최근 수정 2026-05-27), `CLAUDE.md` | LLM-for-OS 방향이 명확히 문서화. README가 “Partial / Future Work” 를 명시적으로 표시. |
| Architecture design | DONE | `architecture_diagram.md` (17 KB), `docs/architecture.md`, `docs/orchestrator_design.md` | Before/Running/After 3-phase 모델, JSON/JSONL 인터페이스 도식까지 정리. |
| Workload definition | DONE | `workloads/*.json` 6 종 | interactive_heavy / long_cpu_bound_first / mixed / priority_sensitive / short_jobs / starvation_risk. |
| Workload analyzer | DONE | `tools/workload_analyzer.py` (209 라인) | 통계 요약 + starvation_risk heuristic. |
| LLM advisor | DONE | `tools/llm_advisor.py` (412 라인), `tools/solar_client.py` (228 라인) | Upstage Solar Pro 3 OpenAI-compatible API, stdlib만 사용 (외부 SDK 없음). |
| Algorithm guard | DONE | `tools/algorithm_guard.py` (626 라인) | 알고리즘/메트릭/파라미터 검증 + algorithm×metric compatibility matrix. |
| Scheduler simulator | DONE | `tools/scheduler_simulator.py` (484 라인) | RR/FCFS/PRIORITY/MLFQ/SJF/SRTF 6 알고리즘 동작. |
| xv6 scheduler integration | DONE | `xv6-riscv/kernel/proc.c` (1172 라인), `xv6-riscv/user/schedtest.c` (195 라인), syscalls `setscheduler` / `getscheduler` | 6 알고리즘 모두 커널 구현. `schedtest` 가 시드/프로파일로 결정성 fork. |
| Trace generation | DONE | `[SCHED]` / `[SCHEDTEST]` 라인 → `tools/trace_parser.py` (233 라인) | ARRIVE / DISPATCH / PREEMPT / EXIT / QUEUE_CHANGE 등 정규화. |
| Metrics evaluator | DONE | `tools/metrics.py` (924 라인) | response/turnaround/waiting/throughput/max_wait/preemption/burst_prediction_error. |
| LLM recommendation evaluator | DONE | `tools/metrics.py` `compute_judgment()` + `pick_best_algorithm()` + `compute_regret()` | regret_score 기반 SUCCESS / NEAR-SUCCESS / FAIL + starvation override. |
| Prompt feedback loop | PARTIAL | `tools/llm_advisor.py --mode feedback` | FAIL 판정 시 `feedback_rules.md` 생성 코드는 있음. 자동 트리거/재호출은 사람이 직접 돌려야 함. |
| Dashboard visualization | DONE | `dashboard_live/` (React/Vite, 17 components), `dashboard_test/` (UI lab) | live-data JSON polling + Gantt + ProcessLanes + TraceStack + 4 종 snapshot 전환. |
| Test / demo readiness | DONE (with caveats) | `scripts/final_demo_check.py`, `scripts/multi_profile_demo_check.py`, GitHub Actions `.github/workflows/` | xv6 snapshot 4종 모두 SUCCESS (regret 0.0). Live xv6 실행은 QEMU 필요. |
| Documentation | DONE | `docs/*.md` 27 개 (architecture, demo_runbook, demo_checklist, presenter_script, RC report, audit 시리즈) | 각 PR 마다 audit 문서가 한 짝씩 붙어 있음. |
| Runtime correction (closed loop) | PARTIAL | `tools/event_detector.py`, `tools/correction_proposer.py`, `tools/correction_guard.py` | preview-only. xv6 apply / `CORRECTION_APPLIED` event 는 Future Work. |
| Feedback Rule Generator (auto) | PARTIAL | `tools/llm_advisor.py --mode feedback` | FAIL 트리거 자동화는 없음. |

---

## 2. Project Goal and Scope

### 2.1 교육적 문제

CPU scheduling은 OS 강의의 핵심이지만, 실제 동작은 보통 “커널 print log”나 “교과서 그림” 으로만 보여진다. 이 프로젝트는 다음 두 가지를 결합한다.

1. **xv6 라는 실제 OS 커널** 에서 CPU scheduling 알고리즘을 직접 실행 (RR / FCFS / PRIORITY+Aging / MLFQ / SJF / SRTF).
2. **LLM (Solar Pro 3)** 이 워크로드 특성을 해석하고 알고리즘을 추천 → Guard 가 검증 → xv6 실행 → 메트릭으로 채점 → LLM 이 결과를 자연어로 설명.

### 2.2 단순 LLM 챗봇 / Python scheduling calculator 와 다른 점

| 비교 대상 | 차이점 |
|---|---|
| 일반 LLM 챗봇 | LLM이 “답만 말함”. 본 프로젝트는 LLM이 **권고만** 하고 **xv6 커널이 실행**, **metrics가 채점**, **GUI가 해설**. LLM의 추천 품질이 regret_score로 정량 검증된다. |
| Python scheduling calculator | 알고리즘을 호스트에서 시뮬레이션만 함. 본 프로젝트는 같은 워크로드를 **실제 xv6 schedtest**(`xv6-riscv/user/schedtest.c`) 로 QEMU에서 돌려 커널 [SCHED] log를 수집한다. |

### 2.3 OS 개념이 들어가는 지점

| OS 개념 | 어디서 구현되는가 |
|---|---|
| process | `xv6-riscv/kernel/proc.c` `struct proc` (ctime, queue_level, wait_ticks, predicted_burst 등 확장 필드 추가됨) |
| process state | RUNNING / RUNNABLE / SLEEPING / ZOMBIE — kernel + simulator 동일 모델 |
| ready queue | RR / MLFQ 모두 RUNNABLE pool에서 선택; MLFQ는 `queue_level 0..2` 3-queue 구성 |
| CPU scheduling | `proc.c` `scheduler()` switch by `sched_mode` (RR/FCFS/PRIORITY/MLFQ/SJF/SRTF) |
| preemption | RR / MLFQ / SRTF: `quantum_expired` PREEMPT event, 시간 슬라이스 만료 시 트랩에서 yield |
| system calls | `setscheduler(int mode)` / `getscheduler(void)` — `xv6-riscv/kernel/sysproc.c:115,127`, `kernel/syscall.c:104-105,135-136`, `user/user.h:27-28` |
| metrics-based evaluation | `tools/metrics.py` — response / turnaround / waiting / throughput / starvation / preemption_count / burst_prediction_error |

---

## 3. System Architecture

### 3.1 전체 실행 흐름 (host orchestrator 기준)

```
workloads/*.json
   └─► tools/workload_analyzer.py          → outputs/.../workload_summary.json
          └─► tools/llm_advisor.py (Solar Pro 3)
                  └─► recommendation.json
                         └─► tools/algorithm_guard.py
                                 └─► guard_decision.json
                                        └─► scripts/orchestrator.py
                                              ├─ backend=xv6  : QEMU + xv6 + schedtest
                                              │                  → outputs/xv6_raw_<algo>_seed<seed>.log
                                              │                  → tools/trace_parser.py → trace_<algo>.jsonl
                                              └─ backend=simulator: tools/scheduler_simulator.py
                                                                  → trace_<algo>.jsonl
                                                                  └─► tools/metrics.py → metrics.json
                                                                        ├─► tools/event_detector.py → runtime_events.json
                                                                        │     └─► tools/correction_proposer.py → correction_proposal.json
                                                                        │              └─► tools/correction_guard.py
                                                                        │                       → correction_guard_decision.json (preview only)
                                                                        ├─► tools/trace_explainer.py (Solar Pro 3) → trace_explanation.json
                                                                        └─► dashboard_live/public/live-data/ (manifest.json + 위 모든 산출물)
                                                                                  → dashboard_live (React/Vite, port 5174)
```

요구사항에서 언급된 `all_metrics.csv`, `evaluation_result.csv` 같은 **CSV** 파일은 본 repo에는 존재하지 않는다. `CLAUDE.md` 규칙에 따라 **모든 모듈 인터페이스는 JSON/JSONL** 이고, evaluator는 `metrics.json` 안의 `judgment` / `regret_score` / `best_algorithm` 필드로 결과를 표현한다.

### 3.2 단계별 책임 / 입출력 / 상태

| # | Stage | 입력 | 출력 | 코드 경로 | 상태 |
|---|---|---|---|---|---|
| 1 | Workload Definition | (수기) | `workloads/*.json` | `workloads/` | DONE — 6 종 |
| 2 | Workload Analyzer | `workloads/<name>.json` | `workload_summary.json` | `tools/workload_analyzer.py` | DONE |
| 3 | LLM Advisor (Solar Pro 3) | `workload_summary.json` (+ optional `feedback_rules.md`) | `recommendation.json` | `tools/llm_advisor.py`, `tools/solar_client.py` | DONE |
| 4 | Algorithm Guard | `recommendation.json` | `guard_decision.json` | `tools/algorithm_guard.py` | DONE |
| 5a | xv6 Execution | `guard_decision.json` + `xv6-riscv/user/schedtest` | `outputs/xv6_raw_<algo>_seed<seed>.log` | `scripts/orchestrator.py` (QEMU 자동화), `kernel/proc.c`, `user/schedtest.c` | DONE (수동 + orchestrator) |
| 5b | Simulator Execution | `guard_decision.json` + workload | `trace_<algo>.jsonl` | `tools/scheduler_simulator.py` | DONE |
| 6 | Trace Parser | raw xv6 log | `trace_<algo>.jsonl` | `tools/trace_parser.py` | DONE |
| 7 | Metrics Evaluator | `trace_<algo>.jsonl` (+ `recommendation.json`) | `metrics.json` (judgment 포함) | `tools/metrics.py` | DONE |
| 8 | Event Detector | trace + metrics | `runtime_events.json` | `tools/event_detector.py` | DONE |
| 9 | Correction Proposer | `runtime_events.json` + recommendation | `correction_proposal.json` (preview only) | `tools/correction_proposer.py` | PARTIAL (preview only, xv6 apply 없음) |
| 10 | Correction Guard | `correction_proposal.json` | `correction_guard_decision.json` (preview only) | `tools/correction_guard.py` | PARTIAL |
| 11 | Trace Explainer (Solar Pro 3) | trace + metrics | `trace_explanation.json` | `tools/trace_explainer.py` | DONE |
| 12 | Feedback Rule Generator | `metrics.json` (judgment=FAIL) | `feedback_rules.md` | `tools/llm_advisor.py --mode feedback` | PARTIAL (수동 실행) |
| 13 | Dashboard | live-data 폴더 전체 | (browser) | `dashboard_live/src/App.jsx` 외 17 components | DONE |
| 14 | Snapshot exporter | live-data + manifest | `live-data/snapshots/<profile>/` | `scripts/export_profile_snapshots.py` | DONE |
| 15 | Contract validator | live-data, snapshots, preview | (exit code) | `tools/validate_dashboard_contract.py` (`--preview`, `--snapshots` 모드) | DONE |

---

## 4. Implemented Features

본 절은 **실제 코드 기준** 으로 구현된 기능만 정리한다. README에만 기재되어 있고 코드가 없는 항목은 §1·§9·§12 에서 PARTIAL / FUTURE로 표기.

### 4.1 Workload Definition / Sample Workloads
- **Status:** DONE.
- **Purpose:** 알고리즘 비교용 결정적 워크로드.
- **Related files:** `workloads/interactive_heavy.json` (25개 interactive process), `long_cpu_bound_first.json`, `mixed_workload.json`, `priority_sensitive.json`, `short_jobs.json`, `starvation_risk.json`.
- **Schema:** list of `{pid, arrival_time, cpu_bursts:[int], io_bursts:[int], priority, label}`.
- **Evidence:** `workloads/interactive_heavy.json:1-292` — 25 short interactive jobs.

### 4.2 Workload Analyzer
- **Status:** DONE.
- **Purpose:** workload JSON → 통계 summary (LLM에게 줄 “관찰 가능한 정보”).
- **Related files:** `tools/workload_analyzer.py:39-147`.
- **Output keys:** `process_count`, `avg_arrival_gap`, `cpu_bound_ratio`, `interactive_ratio`, `avg_priority`, `priority_variance`, `has_starvation_risk` (priority_max ≥ 3 × priority_min heuristic), `burst_count_distribution`, `total_cpu_work`, `workload_file`.
- **Note:** 미래 burst 값은 사용하지만 “총 burst 합”은 통계용일 뿐 — LLM에는 summary만 전달되며, 실제 미래 burst는 **SJF/SRTF predictor 외부에서 그대로 noise 없이 노출되지는 않는다**(`CLAUDE.md`의 burst prediction rule 준수).

### 4.3 LLM Scheduling Advisor (Upstage Solar Pro 3)
- **Status:** DONE.
- **Purpose:** workload summary → 알고리즘 추천 + 파라미터 + 이유.
- **Related files:** `tools/llm_advisor.py:50-167, 313-356` (advise mode), `tools/solar_client.py` (전체).
- **How it works:**
  1. `SolarClient` 가 `.env` 의 `UPSTAGE_API_KEY` 를 stdlib `urllib.request` 로 `POST https://api.upstage.ai/v1/chat/completions` (모델 `solar-pro3`, OpenAI-compatible 스키마).
  2. system prompt가 6개 알고리즘별 params schema를 명시 (`tools/llm_advisor.py:72-103`).
  3. JSON mode (`response_format={"type":"json_object"}`) 로 strict JSON 강제 → `validate()` 가 알고리즘 enum, reason, params 타입 검증.
  4. `schema_compat.normalize_algorithm_name` 으로 dashboard 호환 `recommended_scheduling_algorithm` 필드도 같이 출력.
- **Input:** `outputs/workload_summary.json` + (optional) `outputs/feedback_rules.md`.
- **Output:** `outputs/recommendation.json` (algorithm, params, reason, target_metric, confidence, `_meta`).
- **Evidence from code:** `tools/solar_client.py:81-89` — `UPSTAGE_API_KEY` 없으면 명시적 에러. 키 자체는 `.env` 에만 위치하고 `.gitignore` 로 보호 (`.gitignore:1-3`).
- **Limitations:** 키 없으면 호출 불가. orchestrator는 `--offline-fixture` 옵션으로만 `outputs/_demo_fixtures/recommendation.json` 으로 대체 (그 경우 manifest의 `metadata_source=demo_fallback` 로 표시되어 dashboard 가 `FALLBACK` 배지를 띄움).

### 4.4 Upstage Solar Pro 3 API Integration
- **Status:** DONE (strict 모드는 최신 커밋 `2d67299 feat(runtime): strict Upstage Solar Pro 3 backend; opt-in demo fallback` 에서 도입).
- **Related files:** `tools/solar_client.py` 전체.
- **Key design choices:**
  - 외부 SDK 미사용 (`requirements.txt` 주석에 명시) — stdlib `urllib` 만 사용. 모든 팀원이 `pip install` 없이 돌릴 수 있음.
  - 재시도: 429/500/502/503/504 에 한해 지수 backoff (`solar_client.py:107-130`).
  - `complete_json()` 은 JSON 디코드 실패 시 첫 `{...}` 블록 추출 fallback (`solar_client.py:202-211`).

### 4.5 Algorithm Guard
- **Status:** DONE.
- **Purpose:** LLM 출력이 “xv6에서 안전히 적용 가능한가”를 검증.
- **Related files:** `tools/algorithm_guard.py:1-120, 121-626`.
- **체크 항목:**
  1. JSON 스키마 / 알고리즘 enum (`SUPPORTED_ALGORITHMS = [FCFS, RR, PRIORITY, MLFQ, SJF, SRTF]`).
  2. metric enum + alias 정규화 (`avg_response_time` → `response_time`, …).
  3. Algorithm×Metric Compatibility Matrix (algorithm_guard.py:66-115) — 예: `PRIORITY × starvation = 0.2` 면 REJECT, `MLFQ × response_time = 0.95` 면 APPROVE.
  4. Confidence 임계값 (`CONFIDENCE_REJECT_THRESHOLD = 0.3`).
  5. 파라미터 범위 (`PARAM_RANGES`): RR.quantum 1-100, MLFQ.queues 2-5, MLFQ.quantum list 1-100, aging_threshold 1-10000, boost_interval 10-10000, SJF/SRTF.alpha_percent 0-100 등.
- **Output:** `guard_decision.json` (`accepted` / `rejected` + `fallback_scheduling_algorithm`).
- **Limitations:** 위 표 §1 Notes 대로 SJF/SRTF의 predictor 가용성 체크는 아직 표준화되어 있지 않음.

### 4.6 Scheduler Simulator (host-side dev/fallback)
- **Status:** DONE (개발/대체용 / “xv6 실행 증명 아님”).
- **Related files:** `tools/scheduler_simulator.py` (484 라인).
- **Implemented algorithms:** RR (`_pick_rr`), FCFS (`_pick_fcfs`), PRIORITY+aging (`_pick_priority`, 20-tick aging step), MLFQ (`_pick_mlfq`, 3 큐 + aging promotion `QUEUE_CHANGE` 이벤트), SJF / SRTF (predictor 기반).
- **Trace emission:** `Tracer.emit(tick, event, pid, ...)` → JSONL.
- **Events emitted:** ARRIVE, DISPATCH, PREEMPT, EXIT, QUEUE_CHANGE (+ SLEEP/WAKEUP 모델은 io_bursts 사용 시).

### 4.7 xv6 Kernel Scheduling Algorithms
- **Status:** DONE — 6개 모두 커널 구현.
- **Related files:** `xv6-riscv/kernel/proc.c` (1172 라인, `sched_mode` switch).
- **Key constants/functions:**
  - `sched_mode` enum 0..5 (RR, FCFS, PRIORITY, MLFQ, SJF, SRTF) — `proc.c:31`.
  - `MLFQ_BOOST_THRESHOLD = 20` 라운드 (`proc.c:586`).
  - 5 picker 함수: `pick_rr/pick_fcfs/pick_priority/pick_mlfq/pick_sjf/pick_srtf` (각각 `sched_debug` 로 `[SCHED]` 라인 emit).
  - burst predictor: `proc.c:518` `// ── Burst predictor API (SJF/SRTF) ──` 섹션 — exponential averaging.
  - **System calls:** `setscheduler(mode)` / `getscheduler()` — `sysproc.c:115`, `syscall.c:104,135`, `user/user.h:27`.
- **Trace lines:** `[SCHED] tick=.. algo=.. event=DISPATCH|PREEMPT|EXIT|QUEUE_CHANGE pid=.. queue=..` plus `[SCHEDTEST]` metadata.
- **schedtest workloads:** `xv6-riscv/user/schedtest.c:30-65` 4개 curated profile(interactive, cpu_bound, mixed, priority_sensitive). 시드 인자는 로깅에만 사용 (random 생성은 future).

### 4.8 Trace Event Generation (ARRIVE / DISPATCH / PREEMPT / EXIT)
- **Status:** DONE in both backends.
- **xv6 path:** `proc.c` `sched_trace_*` 함수가 console에 `[SCHED]` 라인 출력 → `trace_parser.py` 가 정규화.
- **Simulator path:** `scheduler_simulator.py` `Tracer.emit()` 가 바로 JSONL 작성.
- **Schema:** `{"tick":int,"algo":str,"event":str,"pid":int, ...}` (`docs/trace_format.md` 참조).
- **Field alias:** `tools/metrics.py:62-66` 가 simulator의 `time`/`algorithm` 별칭도 받아들임.

### 4.9 Metrics Calculation
- **Status:** DONE.
- **Related files:** `tools/metrics.py:517-631` (`compute_metrics`).
- **Computed metrics:**

  | Metric | Formula / Source |
  |---|---|
  | response_time | first_run_time − arrival_time |
  | turnaround_time | finish_time − arrival_time |
  | waiting_time | turnaround_time − total_cpu_burst (kernel은 EXIT 라인에 직접 보고; 없으면 trace dispatch 구간으로 재계산) |
  | throughput | completed_count / total_execution_time |
  | max_waiting_time | per-process waiting의 max |
  | starvation_occurred | `waited > 3 × avg_waiting AND waited ≥ 5 ticks` (`STARVATION_MULTIPLIER=3`, `MIN_STARVATION_WAIT_TICKS=5`) |
  | preemption_count | trace PREEMPT 이벤트 카운트 |
  | burst_prediction_error | SJF/SRTF만; \|predicted − actual\| 평균 |

- **Limitation (문서화됨):** xv6 trace 가 짧을 때(EXIT 5개 안팎) 상대 3× 룰만으로는 1-tick 대기도 starvation으로 잡혀 FAIL이 뜨는 문제가 있어 PR #14 (`fix(metrics): add absolute floor to starvation rule for short xv6 traces`) 로 absolute floor 5 ticks가 추가됨. 동일 이유로 regret 분모에도 absolute floor (#15).

### 4.10 Evaluator (SUCCESS / NEAR-SUCCESS / FAIL)
- **Status:** DONE.
- **Related files:** `tools/metrics.py:414-489`.
- **Judgment logic** (`compute_judgment(regret_score, starvation_occurred)`):

  ```python
  if starvation_occurred: return "FAIL"
  if regret_score is None: return "UNKNOWN"
  if regret_score <= 0.10: return "SUCCESS"
  if regret_score <= 0.25: return "NEAR-SUCCESS"
  return "FAIL"
  ```

- `regret_score = (llm_metric − best) / best` (lower-is-better), `(best − llm_metric) / best` (higher-is-better — throughput).
- `best_algorithm` = target_metric 기준 모든 알고리즘 중 최적.
- 비교 baseline 이 없으면 `_make_synthetic_rr_baseline()` (PR `d546c20`) 으로 합성 RR baseline 생성 — regret을 항상 산출.

### 4.11 Prompt Feedback Loop
- **Status:** PARTIAL.
- **Related files:** `tools/llm_advisor.py:170-305` (`run_feedback`), `FEEDBACK_SYSTEM_PROMPT`.
- **How it works:** `python3 tools/llm_advisor.py --mode feedback` 으로 직접 실행 시 metrics.json의 judgment이 FAIL이면 Solar Pro 3에게 “이 실수를 예방할 룰”을 요청해 `outputs/feedback_rules.md` 작성. advise 모드 다음 실행 시 자동으로 system prompt에 append.
- **What is missing:** orchestrator가 FAIL 판정 후 자동으로 feedback 모드를 호출하지는 않음 (수동). dashboard에도 rule 표시 없음.

### 4.12 Trace Explainer (Solar Pro 3)
- **Status:** DONE.
- **Related files:** `tools/trace_explainer.py` (238 라인).
- **Output schema:** `{scheduling_algorithm, detected_pattern, summary, main_reason, evidence:[], suggestion, runtime_corrections_applied}` — dashboard `LLMExplanation.jsx` 가 그대로 렌더.
- **Note:** `runtime_corrections_applied` 는 LLM에게 맡기지 않고 trace 의 `CORRECTION_APPLIED` 카운트로 덮어씀 (`trace_explainer.py:168-169`).

### 4.13 Runtime Correction Preview (event_detector / proposer / guard)
- **Status:** PARTIAL — preview only, xv6 apply 없음.
- **Related files:**
  - `tools/event_detector.py` (148 라인) — starvation(40 tick 임계) / low_throughput(<0.05) / high_preemption_rate(>0.30/tick) / high_response_time(>10) 탐지.
  - `tools/correction_proposer.py` (235 라인) — 결정성 룰(starvation→aging_strengthen, FCFS+high_response_time→algorithm_change to RR, MLFQ→quantum 조정 등).
  - `tools/correction_guard.py` (172 라인) — proposer 결과를 `algorithm_guard` 의 같은 PARAM_RANGES 테이블로 재검증.
  - dashboard 카드: `dashboard_live/src/components/RuntimeCorrectionPreview.jsx`.
- **Why preview only:** 모든 산출물에 `preview_only=true / applied=false` 명시. xv6 측에는 `CORRECTION_APPLIED` 이벤트나 setscheduler 재호출이 연결되어 있지 않음. README §5.2.1 / §10 에 “Future Work” 명시.
- **Validation:** `tools/validate_dashboard_contract.py --preview` 가 CI에서 preview 산출물 schema를 검사 (`PR #59`).

### 4.14 Dashboard — `dashboard_live` (Primary)
- **Status:** DONE.
- **Related files:** `dashboard_live/src/App.jsx` (256 라인) + 17 components.
- **Components (`dashboard_live/src/components/`):** `Header`, `DemoGuide`, `LLMRecommendation`, `AlgorithmGuard`, `RecommendationEvidence`, `CounterfactualMetricView`, `RuntimeCorrectionPreview`, `EvaluationResult`, `LLMExplanation`, `MainGantt`, `ProcessState`, `TraceStack`, `ProcessLanes`, `WorkloadSummary`, `AlgorithmComparison`, `MetricVisualization`, `Card`, `constants.js`.
- **Data sources (polled every 1 s in live mode):** `dashboard_live/public/live-data/` 의 `manifest.json`, `recommendation.json`, `guard_decision.json`, `workload_summary.json`, `metrics.json`, `trace_explanation.json`, `runtime_events.json`, `correction_proposal.json`, `correction_guard_decision.json`, 6×`trace_<algo>.jsonl`, `snapshots_manifest.json`.
- **Snapshot selector:** header에서 4개 xv6 profile (interactive / cpu_bound / mixed / priority_sensitive) 중 선택 → `live-data/snapshots/<profile>/` 경로 base 로 전환 (PR #37, #38).
- **Backend badge:** `XV6 TRACE` / `SIMULATOR FALLBACK` / `FALLBACK` — manifest의 `metadata_source` 기반.

### 4.15 Dashboard — `dashboard_test` (UI Lab)
- **Status:** DONE.
- **Related files:** `dashboard_test/src/` — 16 components (live 와 비슷하지만 `HeroSection`, `UITestControls` 추가; `RecommendationEvidence` / `CounterfactualMetricView` / `RuntimeCorrectionPreview` / `DemoGuide` 없음).
- **Purpose:** 정적 fixture 로 UI 빠르게 반복.

### 4.16 Dashboard — `dashboard/dashboard.py` (Streamlit, legacy)
- **Status:** DONE but **deprecated** — `docs/implementation_status.md` 가 “legacy fallback only”로 명시. 1112 라인. 발표 데모는 React 버전을 사용.

---

## 5. Major Code Characteristics

### 5.1 Design highlights

1. **모듈은 “단방향 JSON 파이프”로 연결.** 각 단계가 입력 JSON을 받아 다음 JSON을 출력. shared state 없음.  
   → 어떤 단계든 단독 실행 가능, 누가 만들었는지에 상관 없이 교체 가능.

2. **LLM은 절대 scheduler를 제어하지 않는다.** `tools/llm_advisor.py` 는 *recommendation*만 출력하고, `algorithm_guard.py` 가 검증한 뒤에야 simulator/xv6에 도달. `tools/correction_proposer.py` 는 `preview_only=true / applied=false` 로 못박는다. xv6 측에는 LLM이 직접 호출하는 경로가 일체 존재하지 않음.

3. **Algorithm Guard가 검증의 게이트키퍼.** algorithm 미지원, metric mismatch, confidence 부족, 파라미터 범위 위반 → reject + `fallback_scheduling_algorithm`. 이 게이트 덕분에 LLM의 환각도 “xv6 부팅 실패”로 이어지지 않는다.

4. **Trace-driven metrics.** metrics.py는 “어떤 알고리즘이 돌았는가”에 대한 신뢰를 LLM에 두지 않고 **trace event(ARRIVE/DISPATCH/EXIT)에서 재구성**한다. 같은 trace를 누가 만들어도 동일한 metric이 나온다.

5. **Simulator vs xv6 schema 호환.** `tools/schema_compat.py` (298 라인) 가 `algorithm`/`scheduling_algorithm`, `time`/`tick`, `Priority`/`PRIORITY` 등 두 백엔드 표기 차이를 흡수. dashboard 가 두 백엔드 데이터를 차별 없이 소비할 수 있게 함.

6. **Dashboard contract validator.** `tools/validate_dashboard_contract.py` (479 라인) 가 live-data 폴더의 JSON/JSONL이 dashboard 의 기대 스키마와 일치하는지 검사. `--preview` 모드 추가(PR #59)로 runtime correction 산출물도 검증. `--snapshots` 모드(PR #36)로 모든 snapshot 디렉터리 + manifest cross-link 검사.

7. **API key 보안.**
   - `.env` 에만 저장 → `.gitignore:1-3` 로 git에서 차단.
   - `.env.example` 에는 placeholder만 (`UPSTAGE_API_KEY=your_upstage_api_key_here`).
   - `SolarClient.__init__` 가 키 없으면 명시적으로 raise (`solar_client.py:81-89`).
   - PR `0b1903d Add root .gitignore to prevent accidental credential commits` 가 별도로 존재.
   - `requirements.txt` 주석이 `anthropic`/`openai` SDK를 **금지**.
   - **본 보고서에 API 키는 일체 포함하지 않는다.**

8. **Error handling.** Solar API 호출은 stdlib `urllib` + 지수 backoff(`solar_client.py:107-130`); LLM JSON 실패 시 `{...}` 추출 fallback; trace_parser는 mangled line skip(printf interleave 방어, PR #64); metrics.py 는 numerical edge case(division by zero, no baseline)에서 None 반환 후 dashboard 가 "—" 로 표시.

### 5.2 표 — Key Code Modules

| File | Responsibility | Important functions/classes | Input | Output | Maturity |
|---|---|---|---|---|---|
| `tools/workload_analyzer.py` | workload 통계 | `analyze_workload`, `save_summary` | `workloads/*.json` | `workload_summary.json` | DONE |
| `tools/llm_advisor.py` | LLM 추천/feedback | `run_advise`, `run_feedback`, `validate` | summary + (rules) | `recommendation.json`, `feedback_rules.md` | DONE / Feedback PARTIAL |
| `tools/solar_client.py` | Solar Pro 3 HTTP client | `SolarClient.chat / complete_json`, `load_env` | API 호출 | LLM text/JSON | DONE |
| `tools/algorithm_guard.py` | 추천 검증 + matrix | `validate_recommendation`, `evaluate_compatibility`, `PARAM_RANGES`, `COMPATIBILITY_MATRIX` | `recommendation.json` | `guard_decision.json` | DONE |
| `tools/scheduler_simulator.py` | 호스트 시뮬레이터 | `Simulator`, 알고리즘별 `_pick_*` | workload + guard | `trace_<algo>.jsonl` | DONE (개발/fallback) |
| `tools/trace_parser.py` | xv6 raw log → JSONL | `_PREFIXES`, line parser | raw `[SCHED]/[SCHEDTEST]` log | `trace_<algo>.jsonl` | DONE |
| `tools/metrics.py` | 메트릭 + judgment | `compute_metrics`, `compute_regret`, `compute_judgment`, `pick_best_algorithm`, `evaluate_run` | trace + recommendation + baselines | `metrics.json` | DONE |
| `tools/event_detector.py` | 런타임 문제 탐지 | `detect` (4 rule) | trace + metrics | `runtime_events.json` | DONE |
| `tools/correction_proposer.py` | 결정성 correction rule | `propose`, `_pick_event` | runtime_events + recommendation | `correction_proposal.json` (preview) | PARTIAL |
| `tools/correction_guard.py` | correction 재검증 | guard re-run | proposal | `correction_guard_decision.json` (preview) | PARTIAL |
| `tools/trace_explainer.py` | LLM 자연어 해설 | `summarize_trace`, `validate` | trace + metrics + rec | `trace_explanation.json` | DONE |
| `tools/schema_compat.py` | 두 백엔드 스키마 호환 | `normalize_algo`, `normalize_target_metric`, alias 맵 | any JSON | normalized | DONE |
| `tools/validate_dashboard_contract.py` | dashboard 계약 검증 | `--preview`, `--snapshots` 모드 | live-data | exit code | DONE |
| `scripts/orchestrator.py` | host control plane | `--backend xv6/simulator`, QEMU 자동화 | profile | live-data + manifest | DONE |
| `scripts/final_demo_check.py` | demo 사전점검 | 빌드 + 시뮬 smoke | — | log | DONE |
| `scripts/multi_profile_demo_check.py` | 4 profile 사전점검 | 반복 호출 | — | log | DONE |
| `scripts/export_profile_snapshots.py` | snapshot 출판 | per-profile copy | live-data | `snapshots/<profile>/` | DONE |
| `scripts/correction_preview_smoke.py` | preview 산출물 offline smoke | 합성 | — | preview JSON | DONE |
| `scripts/analyze_algorithm_winners.py` | per-metric 1등 표 | comparison parse | metrics | table | DONE |
| `xv6-riscv/kernel/proc.c` | 6개 scheduler 본체 | `scheduler`, `pick_*`, syscalls | xv6 | `[SCHED]` log | DONE |
| `xv6-riscv/user/schedtest.c` | 결정적 워크로드 user prog | `find_workload`, `algo_mode`, fork loop | 인자 | `[SCHEDTEST]` log | DONE |
| `dashboard_live/src/App.jsx` | React 메인 | `loadAll`, snapshot 선택, polling | live-data | UI | DONE |

---

## 6. Scheduling Algorithms and Evaluation Logic

### 6.1 알고리즘별 특성과 유리한 워크로드

| Algorithm | 특성 | 유리한 워크로드 | 코드 |
|---|---|---|---|
| RR (Round Robin) | preemptive, equal time-slice | interactive 다수, 공정성 | `proc.c` `_pick_rr` 영역, `simulator._pick_rr` |
| FCFS | non-preemptive, arrival 순 | 짧고 비슷한 burst만 / batch | `proc.c:652-682`, `simulator._pick_fcfs` |
| PRIORITY + Aging | priority 기반, 20-tick aging | 중요 jobs 응답 우선 | `proc.c:..-731`, `simulator._pick_priority` |
| MLFQ | 3-queue + quantum [2,4,8] + aging promotion | 짧은 interactive + 긴 CPU 혼합 | `proc.c:741-786`, `simulator._pick_mlfq` |
| SJF (predicted) | non-preemptive, exponential averaging | 짧은 burst 평균 응답 줄이기 | `proc.c:809-843` |
| SRTF (predicted) | preemptive SJF | 짧은 burst가 자주 도착 | `proc.c:853-889` |

### 6.2 메트릭 공식 (재기재)

```
response_time   = first_run_time - arrival_time
turnaround_time = finish_time - arrival_time
waiting_time    = turnaround_time - total_cpu_burst_time
throughput      = completed_process_count / total_execution_time
```

### 6.3 추천 평가 규칙 (코드 기준)

- `tools/metrics.py:457-467` `compute_judgment`:
  - `starvation_occurred=True` → **즉시 FAIL**.
  - 그렇지 않으면 `regret_score ≤ 0.10 → SUCCESS`, `≤ 0.25 → NEAR-SUCCESS`, else **FAIL**.
- `tools/metrics.py:414-454` `compute_regret`:
  - lower-is-better metric: `regret = (llm − best) / best`.
  - higher-is-better metric(`throughput`): `regret = (best − llm) / best`.
  - 음수는 0으로 clamp.
- baseline이 없으면 PR `d546c20` 으로 합성 RR baseline 생성. xv6의 짧은 trace 에서는 PR #15 가 분모에 absolute floor 를 추가.

### 6.4 데모 metrics 예시 (`outputs/_demo_fixtures/metrics.json` 발췌)

| Algorithm | avg_response_time | avg_waiting_time | avg_turnaround | throughput | preemption | judgment |
|---|---:|---:|---:|---:|---:|---|
| MLFQ (LLM 선택) | **1.8** | 14.8 | 24.8 | 0.089 | 9 | **SUCCESS** (regret 0.07) |
| RR | 3.2 | 20.0 | 30.0 | 0.10 | 10 | NEAR-SUCCESS |
| Priority | 8.4 | 10.8 | 21.2 | 0.104 | 2 | NEAR-SUCCESS |
| FCFS | 18.4 | 18.4 | 28.8 | 0.096 | 0 | FAIL |
| SJF | 12.4 | 12.4 | 22.8 | 0.096 | 0 | NEAR-SUCCESS |
| SRTF | 4.8 | 7.0 | 17.4 | 0.104 | 3 | SUCCESS |

LLM이 `target_metric=avg_response_time` 에서 MLFQ 추천 → 실제 최저 response_time 알고리즘이 MLFQ, regret 0.07 < 0.10 → SUCCESS.

---

## 7. Dashboard and Visualization

### 7.1 UI 구조 (`dashboard_live`)

- 3-column layout (`App.jsx:216-253`).
- **Left:** DemoGuide → LLMRecommendation → AlgorithmGuard → RecommendationEvidence → CounterfactualMetricView → RuntimeCorrectionPreview → EvaluationResult → LLMExplanation.
- **Center:** MainGantt → ProcessState → TraceStack.
- **Right:** ProcessLanes → WorkloadSummary → AlgorithmComparison → MetricVisualization.
- Header: backend badge, snapshot selector, manifest version, last-updated 시각, live mode toggle.

### 7.2 데이터 소스

- `dashboard_live/public/live-data/` (orchestrator가 publish).
- 폴링 1 초 간격(`POLL_INTERVAL_MS = 1000`), `manifest.json` 의 `version:updated_at` 키가 바뀔 때만 reload.
- snapshot 모드: `live-data/snapshots/<profile>/` 로 base 만 바꿈, polling 비활성화 (정적이므로).

### 7.3 시각화 요소별 현재 수준

| 요소 | 컴포넌트 | 현재 수준 | 비고 |
|---|---|---|---|
| Gantt chart | `MainGantt.jsx` + `ProcessLanes.jsx` | DONE | tick 축 + algo 별 색, PR #4 (`Polish React dashboard`) |
| Process state | `ProcessState.jsx` | DONE | RUNNING/RUNNABLE/SLEEP/ZOMBIE 표 |
| Ready queue (MLFQ) | `ProcessLanes.jsx` queue level 색 표시 | PARTIAL | 전용 “queue 보기”는 lanes 색으로 표현 |
| Trace event stack | `TraceStack.jsx` | DONE | scroll 가능한 이벤트 리스트 |
| Workload summary | `WorkloadSummary.jsx` | DONE | analyzer 출력 그대로 |
| LLM Recommendation | `LLMRecommendation.jsx` | DONE | algorithm + params + reason + target_metric |
| Algorithm Guard | `AlgorithmGuard.jsx` | DONE | accept/reject + 이유 |
| Recommendation Evidence | `RecommendationEvidence.jsx` (PR #32) | DONE | LLM reason + workload traits + guard score + provenance 한 카드 |
| Metric comparison table | `AlgorithmComparison.jsx` | DONE | 알고리즘×metric 표 |
| Metric visualization | `MetricVisualization.jsx` | DONE | bar/glow + metric selector |
| Counterfactual metric view | `CounterfactualMetricView.jsx` (PR #43, #44) | DONE | “target metric이 바뀌면 누가 1등?” |
| Evaluation result | `EvaluationResult.jsx` | DONE | judgment(SUCCESS/NEAR-SUCCESS/FAIL) + regret + direction-aware metric 비교 |
| LLM Explanation | `LLMExplanation.jsx` | DONE | trace_explanation.json 렌더 |
| Runtime correction preview | `RuntimeCorrectionPreview.jsx` (PR #54, #56) | DONE (preview only) | 데이터 없으면 카드 숨김 |
| Demo guide | `DemoGuide.jsx` (PR #46, #47) | DONE | 5-step click-to-flash |
| Live mode | `App.jsx` polling | DONE | snapshot 모드와 상호배타 |

### 7.4 `dashboard_live` vs `dashboard_test` vs `dashboard/`

| 항목 | `dashboard_live` | `dashboard_test` | `dashboard/` |
|---|---|---|---|
| 목적 | 발표용, 실데이터 | UI lab, fixture | legacy Streamlit |
| 데이터 | `live-data/` 동적 | `src/data/` 정적 fixture | local JSON |
| 컴포넌트 수 | 17 | 16 (Hero/UITestControls 추가, evidence/counterfactual/correction/demoguide 없음) | 단일 Python 파일 |
| 추천 사용 | **데모용 메인** | UI 작업 시 | (사용 안 함) |

---

## 8. Development Process Summary

### 8.1 큰 흐름 (git log + PR 메시지 기반)

1. **Phase 1 — 모듈별 prototype.** workload_analyzer / scheduler_simulator / xv6 RR-baseline 부터 시작. workload JSON 포맷 정비(PR series `b589481..63c7207`).
2. **Phase 2 — LLM 통합.** Solar Pro 3 client (`tools/solar_client.py`) 작성 → `llm_advisor` → `algorithm_guard` 추가. metrics + evaluator 동시 작업.
3. **Phase 3 — xv6 scheduler 확장.** `setscheduler/getscheduler` syscall, FCFS/PRIORITY/MLFQ 추가, 마지막에 SJF/SRTF + burst predictor (`3031767 Add prediction-based SJF and SRTF`).
4. **Phase 4 — Dashboard 분기.** Streamlit dashboard 에서 React/Vite로 이동 (`c88bba6 Add React/Vite observability dashboard`). dashboard 를 test/live 둘로 split (`c95b264 feat: split dashboard into test/live apps`).
5. **Phase 5 — Orchestrator refactor.** “호스트 control plane” 도입 (`f6911dd feat(orchestrator): host-side control plane with simulator + xv6 backends`). xv6를 “정말 실행되는 백엔드”로 위치 변경, simulator는 dev/fallback.
6. **Phase 6 — Demo readiness.** trace explainer, demo runbook, presenter script, defense notes, RC report, snapshot exporter (4 profile), Recommendation Evidence / Counterfactual / DemoGuide / RuntimeCorrectionPreview 카드, CI(QEMU 없는 lightweight), validator `--preview`/`--snapshots` 모드. PR #20 ~ #69 가 대부분 이 단계.
7. **Phase 7 — RC freeze + revert.** PR #67/#68/#69 (step layout 마이그레이션)이 RC freeze 범위를 벗어나 PR #70으로 revert(`9af5cfb`).
8. **Phase 8 (현재 branch `feat/upstage-runtime-strict`):** Upstage Solar Pro 3 strict 백엔드 도입 — `2d67299 feat(runtime): strict Upstage Solar Pro 3 backend; opt-in demo fallback`.

### 8.2 표 — Development Timeline (주요 사건만)

| Date / Commit | Change | Related files | Impact | Status |
|---|---|---|---|---|
| `0b1903d` | root `.gitignore` for credentials | `.gitignore` | API 키 사고 방지 | DONE |
| PR #3 / `4742558..6c899e3` | xv6 scheduler harness | `kernel/proc.c`, `user/schedtest.c` | 6 알고리즘 실험 가능 | DONE |
| `3031767` PR #4 | SJF/SRTF + predictor in xv6 | `proc.c` (predictor API), `schedtest.c` | predict 기반 알고리즘 비교 가능 | DONE |
| `c88bba6` | React/Vite dashboard + host tool pipeline | `dashboard_live/`, `tools/` | Streamlit 탈출, 본격 GUI | DONE |
| PR #6/#7 / `c95b264` `42840d1` | dashboard split test/live | `dashboard_live`, `dashboard_test` | UI iteration vs 실데이터 분리 | DONE |
| `995bc53` | Trace Explainer 추가 | `tools/trace_explainer.py` | After-running LLM 해설 | DONE |
| PR #9 `fed68dc` | live judgment를 selected metric으로 재계산 | dashboard | metric 바꿔도 판정 즉시 갱신 | DONE |
| `f6911dd` | Orchestrator 도입 (control plane) | `scripts/orchestrator.py` | xv6/simulator 백엔드 일원화, schema adapter, dashboard backend 배지 | DONE |
| `c8e95e5` | schedtest seed/profile + richer traces | `user/schedtest.c`, `kernel/proc.c` | 결정적 xv6 실행, [SCHEDTEST] 메타 | DONE |
| PR #11 `108da45` | metrics: derive xv6 arrival_time from PROC_DEF | `tools/metrics.py` | xv6 trace 정확도 ↑ | DONE |
| PR #12 `f43687f` | schedtest: planned arrival 까지 fork 지연 | `user/schedtest.c` | 도착시각 통제 정확 | DONE |
| PR #14/#15 | starvation rule + regret 분모에 absolute floor | `tools/metrics.py` | 짧은 xv6 trace에서 잘못된 FAIL 제거 | DONE |
| PR #16 `b68708e` | validator strict mode + manifest checks | `tools/validate_dashboard_contract.py` | dashboard contract CI 보호 | DONE |
| PR #17 `0161b9d` | `final_demo_check.py` + printf interleave 복구 | `scripts/`, `tools/` | 사전점검 단일 명령 | DONE |
| PR #25/#26/#27 | presenter script + multi_profile_demo_check + CI | `docs/`, `scripts/`, `.github/workflows/` | demo prep 자동화 | DONE |
| PR #35..#38 | 4 xv6 profile snapshot 출판 + selector | `scripts/export_profile_snapshots.py`, `dashboard_live` | dashboard 가 4 시나리오 즉시 전환 | DONE |
| PR #41/#43/#44 | 알고리즘 다양성 audit + Counterfactual view + winners table | `scripts/analyze_algorithm_winners.py`, `dashboard_live/.../CounterfactualMetricView.jsx` | “MLFQ만 답이 아님” 정량 증거 | DONE |
| PR #52..#59 | Runtime correction **preview** (proposer/guard/RuntimeCorrectionPreview + smoke + validator `--preview`) | `tools/correction_*`, `dashboard_live`, `scripts/correction_preview_smoke.py` | preview-only loop 가시화 | PARTIAL (xv6 apply 없음) |
| PR #62/#65 | RC YELLOW → GREEN (RR row 이상치 해결) | `docs/final_release_candidate_report.md`, `scripts/orchestrator.py` | 발표 준비 완료 신호 | DONE |
| PR #67/#68/#69 → PR #70 | step layout 마이그레이션 후 revert | `dashboard_live` | RC freeze 외 작업 되돌림 | REVERTED |
| `2d67299` (현 branch) | Strict Solar Pro 3 backend + opt-in demo fallback | `tools/solar_client.py`, `scripts/orchestrator.py` | API 키 없으면 명시 fail | DONE |

### 8.3 해결한 문제 / 남은 문제

| 해결한 문제 | 어떻게 |
|---|---|
| xv6 짧은 trace에서 starvation 오판정 | starvation에 absolute floor 추가 (PR #14) + regret 분모 floor (PR #15) |
| printf interleave 로 `RUN_BEGIN` 깨짐 | orchestrator 윈도잉을 substring 매칭으로 완화 (PR #64); trace_parser 가 깨진 라인 skip |
| LLM이 `[1m]` 같은 marker로 dashboard 깨뜨림 | strict JSON mode + validator |
| dashboard_live가 fallback 데이터로 헷갈리게 표시 | manifest `metadata_source` + 배지 (`SIMULATOR FALLBACK` / `FALLBACK`) + 노란 배너 |
| MLFQ가 “항상 정답”으로 보이는 발표 약점 | analyze_algorithm_winners + CounterfactualMetricView 로 metric별 우승자 다양함을 보여줌 |

| 남은 문제 | 위치 |
|---|---|
| Runtime correction 의 closed-loop xv6 apply | `tools/correction_proposer.py` 이후가 모두 preview only |
| Feedback rule 자동 트리거 | `tools/llm_advisor.py --mode feedback` 가 수동 실행 |
| MLFQ 외 알고리즘 워크로드 cover 부족 | 4 profile 모두 LLM이 MLFQ 추천 → 다양성 audit(`docs/algorithm_decision_diversity_audit.md`)에서 인지 |
| QEMU 없는 환경 CI는 lightweight smoke 만 | 진짜 xv6 실행 CI는 없음 |

---

## 9. Current Limitations and Risks

1. **xv6 integration은 “실제 + optional”의 절충.** `scripts/orchestrator.py --backend xv6` 가 실제로 QEMU 부팅 + `schedtest` 실행 + 콘솔 capture까지 한다. 단, 발표 환경에서 QEMU가 막혀 있을 때를 대비해 simulator fallback과 4개 xv6 snapshot이 출판되어 있다.
2. **xv6 traces are short (~30–80 events per algorithm).** `schedtest` 의 curated profile은 4-5개 child만 fork. metric 절댓값보다는 알고리즘간 비교에 적합.
3. **LLM API 호출은 실제(real).** `tools/solar_client.py` 가 진짜 `https://api.upstage.ai/v1/chat/completions` 호출. 키가 없으면 orchestrator 가 `--offline-fixture` 일 때만 `outputs/_demo_fixtures/recommendation.json` 으로 대체.
4. **Trace schema 안정성:** simulator(`time`/`algorithm`)와 xv6(`tick`/`algo`) 표기가 다르지만 `tools/schema_compat.py` 와 `tools/metrics.py:62-77` `normalize_event` 가 흡수. 새 이벤트 추가 시는 양쪽을 동시에 봐야 함.
5. **Metrics 정확성:** trace로부터 재계산 + xv6의 EXIT 라인 직접 보고 둘 다 지원. 짧은 trace에서의 starvation/regret edge case는 PR #14/#15 로 보강.
6. **Dashboard 연동 범위:** runtime correction 카드는 “preview” 라벨 명시. 데이터 없으면 자동 숨김. snapshot selector는 정적이므로 polling 안 함.
7. **Demo scenario:** `docs/demo_runbook.md`, `docs/demo_checklist.md`, `docs/presenter_script.md` 세 종이 한 묶음. README §10 의 “starvation 시나리오”는 closed-loop가 미완이라 Future Work라고 명시.
8. **Test coverage:** unit-test 디렉터리가 없다. 대신 `scripts/final_demo_check.py`, `scripts/multi_profile_demo_check.py`, `scripts/correction_preview_smoke.py`, `tools/validate_dashboard_contract.py` 가 “end-to-end smoke + 계약 검증” 역할. CI는 `.github/workflows/` 에 lightweight smoke 만 (QEMU 미사용).
9. **README 실행 명령 일치성:** README와 docs의 명령(`make qemu`, `python3 tools/scheduler_simulator.py`, `streamlit run dashboard/dashboard.py`, `cd dashboard_live && npm run dev`)이 실제 파일과 일치. 단 `tools/scheduler_simulator.py` 는 인자 없이 실행하면 워크로드/가드 인자 요구 → orchestrator 경유가 표준 경로.
10. **API key / secret 관리:** `.gitignore` 보호 + `.env.example` placeholder + `SolarClient` 가 키 없으면 raise. **보고서에 키 절대 미포함.**
11. **발표 관점에서 교수님이 짚을 수 있는 약점:**
    - “LLM이 매번 MLFQ만 추천하면 LLM의 가치가 뭐냐?” → CounterfactualMetricView + algorithm_decision_diversity_audit 로 metric별 우승자가 다르다는 정량 증거 준비됨.
    - “runtime correction이 closed-loop 인가?” → 솔직하게 preview only. README/docs/§12.1에 명시.
    - “xv6 schedtest는 실제 OS workload가 아니지 않나?” → 결정성 / 재현성 / 강의자료 관점에서 의도된 선택. `docs/presentation_defense_notes.md` 에 답변 정리.

---

## 10. Next Action Plan

### 표 — Next Tasks

| Priority | Task | Why it matters | Related files | Owner role (추정) | Expected output | Risk if not done |
|---|---|---|---|---|---|---|
| **P0** | 발표용 dashboard 한 번 더 dry-run + screenshot 캡처 (4 profile 모두 swipe) | 발표날 라이브 실패 대비 | `dashboard_live/public/live-data/snapshots/*`, `docs/presenter_script.md` | Frontend/Demo lead | `docs/final_demo_dry_run_report.md` 갱신 + screenshots | 발표 사고 |
| **P0** | `.env` 누락 케이스의 사용자 가이드 한 번 더 확인 | 시연 시 API 키 미세팅 흔함 | `tools/solar_client.py`, `.env.example`, README §3 | Backend/LLM | README 또는 demo_runbook 짧은 trouble-shoot 단락 | LLM 호출 실패 → demo 멈춤 |
| **P0** | 4 xv6 snapshot 무결성 재확인 (`tools/validate_dashboard_contract.py --snapshots`) | dashboard “FALLBACK 배지” 가 발표날 뜨면 안 됨 | `dashboard_live/public/live-data/`, validator | DevOps | exit 0 로그 | 시연 신뢰도 손상 |
| **P0** | RC freeze 외 진행 중인 branch (`feat/upstage-runtime-strict`) 머지 여부 결정 | strict 모드 vs RC GREEN main 의 불일치 정리 | `scripts/orchestrator.py`, `tools/solar_client.py` | Tech lead | 머지 또는 발표 후 머지 결정 commit | 발표 직전 회귀 |
| P1 | Runtime correction의 xv6 apply step 시작 (`setscheduler` 재호출 + `CORRECTION_APPLIED` event emit) | closed-loop 가 본 프로젝트의 차별점 | `kernel/proc.c`, `user/schedtest.c`, `scripts/orchestrator.py` | xv6 lead | xv6 apply 경로 + 새 event | “Future Work” 라벨이 영구화 |
| P1 | Feedback loop 자동 트리거 (orchestrator가 FAIL 시 `--mode feedback` 호출 후 next-run prompt에 자동 append) | LLM이 “학습”하는 인상 강화 | `scripts/orchestrator.py`, `tools/llm_advisor.py` | LLM lead | 자동 호출 + dashboard rule 카드 | LLM의 학습 측면 미증명 |
| P1 | MLFQ 외 추천이 나오게 하는 workload (예: 짧은 batch만 → SJF, single CPU bound → FCFS) 추가 + LLM 응답 정량 비교 | 추천 다양성 “실증” | `workloads/`, `docs/algorithm_decision_diversity_audit.md` | LLM/eval | 신규 workload + winners 표 갱신 | 발표 질문 약점 잔존 |
| P1 | `tools/algorithm_guard.py` 의 SJF/SRTF predictor 가용성 체크 표준화 | edge case 안전 | `tools/algorithm_guard.py` | guard owner | 새 check + 테스트 | SJF/SRTF 추천이 깨질 수 있음 |
| P2 | unit-test 추가 (`tools/metrics.py` judgment, `tools/correction_proposer.py` 룰 테이블) | regression 방어 | `tests/` 신규 | dev | pytest 통과 | 변경 시 회귀 가능성 |
| P2 | Streamlit `dashboard/dashboard.py` 제거 또는 archive 분기 | repo 군더더기 정리 | `dashboard/` | repo 정리 | 삭제 PR | (없음) |
| P2 | Live mode polling을 SSE/WebSocket로 교체 | UX 개선 | `dashboard_live/src/data/`, `scripts/` | frontend | streaming endpoint | (없음) |
| P2 | xv6 schedtest 에 더 큰 workload (10-20 child) | metric scale 다양화 | `xv6-riscv/user/schedtest.c` | xv6 | 신규 profile | (없음) |

P0 항목은 모두 “demo가 망가지지 않게 하는 일” 만.

---

## 11. Final Demo Readiness

| 항목 | 점수 (0~5) | 근거 |
|---|---:|---|
| End-to-end pipeline readiness | **5** | simulator 백엔드는 완전 자동 (`scripts/orchestrator.py --backend simulator`). xv6 백엔드도 QEMU 자동화 완료. 4 profile snapshot 출판으로 QEMU 없는 환경에서도 시연 가능. dashboard contract validator + CI smoke. |
| xv6 integration readiness | **4** | 6 알고리즘 모두 커널 구현, syscall 추가, `schedtest` 결정성 워크로드, orchestrator가 QEMU build/boot/capture. 단 closed-loop runtime correction 의 apply step 미구현. |
| LLM advisor readiness | **4** | Solar Pro 3 strict 호출 + JSON 강제 + validator + feedback 모드. 자동 feedback 트리거는 미완. 4 profile 모두 MLFQ 로 수렴하는 추천 다양성 약점. |
| Metrics / evaluation readiness | **5** | response/turnaround/waiting/throughput/starvation/regret/judgment 완성. starvation 절대값 floor + 합성 RR baseline + best_algorithm winners. |
| Dashboard readiness | **5** | 17 컴포넌트, snapshot selector, backend 배지, DemoGuide, RuntimeCorrectionPreview, Recommendation Evidence, Counterfactual view. `dashboard_live` 가 발표용 메인. |
| Documentation readiness | **5** | README 29 KB + `docs/*.md` 27 종. presenter_script / demo_runbook / demo_checklist / defense_notes / RC report / multiple audits. |

**총평:** 시연 자체는 **GREEN** (PR #65). xv6+QEMU 가 막힌 환경에서도 snapshot 4종으로 풀 시연 가능. closed-loop correction이 “Future Work” 라는 점만 미리 말해두면 평가 약점은 없음.

---

## 12. Conclusion

### 12.1 강점 3

1. **“LLM은 추천만, xv6가 실행”의 안전 설계가 코드 레벨에서 강제됨.** `algorithm_guard` + `correction_guard` 가 LLM 출력이 커널까지 도달하기 전에 두 단계로 검증한다. `correction_proposer/guard` 산출물은 `preview_only=true / applied=false`. LLM 호출 경로는 `tools/solar_client.py` 하나로 격리.
2. **모듈 간 인터페이스가 JSON/JSONL 일색이라 누가 만들었는지 무관하게 교체·검증 가능.** `tools/schema_compat.py` 가 simulator/xv6 두 백엔드의 trace schema 차이를 흡수하고, `tools/validate_dashboard_contract.py` 가 dashboard 계약을 CI로 보장.
3. **xv6 6개 알고리즘이 정말로 커널에 구현되어 있고, `schedtest` + orchestrator 로 결정적으로 실행된다.** 단순 시뮬레이터 비교가 아니라 “실제 OS 커널 trace” 로 metric을 채점한다. 4 profile snapshot 까지 미리 출판되어 발표 환경에서도 즉시 시연 가능.

### 12.2 가장 위험한 약점 3

1. **Closed-loop runtime correction이 preview-only.** README의 “starvation 시나리오” 의 클라이맥스(LLM 교정 → xv6 적용 → 자동 회복)가 실제 데모에는 없다. preview UI가 있어 “있는 척”으로 보일 위험.
2. **LLM 추천 다양성 부족.** 4 profile 모두 MLFQ를 추천 → “이 LLM은 그냥 MLFQ 봇 아니냐” 질문에 정량 답변(Counterfactual + winners)을 미리 준비해 두긴 했지만 새 workload(예: 순수 batch) 로 실제 SJF/FCFS 추천을 받아내는 실증이 더 필요.
3. **자동화 테스트 부재.** 단위 테스트가 없고 보호망은 smoke 스크립트 + contract validator + CI lightweight 만. metric 계산 / judgment / correction 룰의 회귀가 PR 단위로 감지되지 않는다.

### 12.3 마감 전 반드시 끝내야 할 것 3

1. **현재 branch `feat/upstage-runtime-strict` 머지 정책 결정 + 모든 4 snapshot 의 validator 통과 재확인** (위 P0).
2. **demo dry-run 1회 + screenshot 캡처 갱신** (위 P0).
3. **README/demo_runbook 의 “API 키 없을 때 fallback 모드 띄우는 법” 한 단락 보강** — `--offline-fixture` 플래그와 `FALLBACK` 배지 의미를 시연자가 즉답할 수 있도록 (위 P0).

---

### Appendix — 분석 메타

- **분석한 주요 파일 수:** 약 35 개 (Python 18, JSX 17, xv6 C 2, JSON/JSONL/MD 다수의 sampling 포함).
- **총 코드량 (Python+JSX+xv6 C 발췌):** Python tools+scripts ≈ 6.3 k LOC, dashboard React ≈ 17 components, xv6 핵심 ≈ 1.4 k LOC.
- **Git 분석 범위:** 최근 100 commits + main의 PR 메시지.
- **확인 불가 항목:** 실제 QEMU 부팅 결과 (본 분석 환경에서 QEMU 미실행). 대신 `outputs/xv6_raw_*_seed42.log`, `outputs/check_xv6_scheduler_*.log`, `outputs/build_*.log` 의 존재로 과거 실행 흔적은 확인됨.
- **본 보고서에 API 키 / `.env` 내용 / 외부 secret 일체 포함하지 않음.**

