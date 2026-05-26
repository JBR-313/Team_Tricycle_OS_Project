# LLM Sched Copilot — 프로젝트 진행상황

> 작성일: 2026-05-25  
> 현재 브랜치: `feature/live-dashboard-split`  
> 메인 브랜치: `main`

---

## 1. 프로젝트 개요

**LLM Sched Copilot**은 LLM을 xv6 OS의 스케줄링 의사결정 보조 레이어로 활용하는 LLM-for-OS 프로젝트다.

- LLM은 스케줄러가 **아니다** — xv6가 실행 권한을 갖는다
- LLM은 워크로드를 분석하고, Scheduling Algorithm을 추천하고, 트레이스를 설명하고, 문제 발생 시 보정 제안을 한다
- Algorithm Guard가 모든 LLM 출력을 검증한 후 적용한다

```
워크로드 정의 → LLM 추천 → Algorithm Guard → xv6 실행 → 트레이스 수집
→ 메트릭 평가 → 런타임 보정 제안 → 트레이스 설명 → GUI 대시보드
```

---

## 2. 시스템 아키텍처 — 3단계

### Phase 1: Before Running (추천 레이어)
```
workloads/*.json
  → workload_analyzer.py       → workload_summary.json
  → llm_advisor.py (Solar Pro 3)  → recommendation.json
  → algorithm_guard.py         → guard_decision.json
```

### Phase 2: Running (실행 & 수집 레이어)
```
guard_decision.json
  → [xv6 커널 | scheduler_simulator.py]  → trace_*.jsonl
  → metrics.py                           → metrics.json
  → event_detector.py                    → runtime_events.json
  → [Runtime Correction Proposer + LLM]  → correction.json
```

### Phase 3: After Running (분석 & 시각화)
```
trace.jsonl + metrics.json
  → LLM Trace Explainer     → trace_explanation.json
  → Feedback Rule Generator → feedback_rules.md  (FAIL 시만)
  → dashboard_live/         → React GUI 대시보드
```

---

## 3. 구현 현황

### 3-1. xv6 커널 (`xv6-riscv/kernel/`) ✅ 완료

| 파일 | 변경 내용 |
|------|---------|
| `proc.h` | `SCHED_RR~SCHED_SRTF` 상수, `struct proc` 필드 9개 추가 |
| `proc.c` | 6가지 Scheduling Algorithm 구현 (RR, FCFS, Priority+Aging, MLFQ, SJF, SRTF) |
| `trap.c` | 타이머 인터럽트 처리 — SJF 비선점 / SRTF 매 tick 선점 / `cur_burst_run` 누적 |
| `sysproc.c` | `setscheduler`, `getscheduler`, `setpriority`, `getpriority`, `setpredictor`, `getpredictor` 6개 시스템콜 구현 |
| `syscall.c` / `syscall.h` | 시스템콜 디스패치 테이블에 신규 syscall 등록 |
| `defs.h` | 커널 내부 API 선언 |

**추가된 `struct proc` 필드:**
```c
int priority;           // 스케줄링 우선순위 (낮을수록 높은 우선순위)
int ctime;              // 프로세스 생성 tick (FCFS/Priority tie-break)
int rtime;              // 총 CPU 사용 tick
int queue_level;        // MLFQ 큐 레벨 (0=최고, 2=최저)
int ticks_in_level;     // 현재 MLFQ 큐 내 사용 tick 수
int wait_ticks;         // RUNNABLE 상태 대기 tick 수
int predicted_burst;    // 다음 CPU 버스트 예측값 (SJF/SRTF)
int cur_burst_run;      // 현재 버스트에서 관측된 CPU tick (타이머 누적)
int ready_since_tick;   // RUNNABLE 진입 tick (SJF/SRTF tie-break)
```

**SJF/SRTF 예측 방식 (지수 평균):**
```
new_prediction = (alpha * last_observed_burst + (100 - alpha) * old_prediction) / 100
```
- 실제 미래 버스트 값은 LLM에 절대 전달하지 않음
- 커널은 이미 관측된 `cur_burst_run`만으로 예측 갱신

**QEMU 검증 완료:**
- `make fs.img` 경고·오류 없이 빌드 성공
- `schedtest` — RR, FCFS, Priority, MLFQ, SJF, SRTF 모두 정상 완료
- `predtest` — predictor 파라미터 적용, 예측값 수렴 확인

> **현재 상태:** xv6 SJF/SRTF 구현은 로컬 검증 완료, **미커밋 상태**

---

### 3-2. Python 도구 파이프라인 (`tools/`) ✅ 완료

| 모듈 | 역할 | 상태 |
|------|------|------|
| `workload_analyzer.py` | 워크로드 특성 분석 (CPU/IO 비율, 우선순위 분산, 기아 위험도) | ✅ |
| `solar_client.py` | Upstage Solar Pro 3 API 클라이언트 | ✅ |
| `llm_advisor.py` | LLM에 워크로드 요약 전달 → Scheduling Algorithm 추천 수신 | ✅ |
| `algorithm_guard.py` | 추천 검증: 알고리즘 지원 여부, 파라미터 범위, JSON 스키마 | ✅ |
| `scheduler_simulator.py` | 호스트 측 스케줄러 시뮬레이터 (xv6 없이 실행 가능) | ✅ (SJF/SRTF 부분 미완) |
| `trace_parser.py` | xv6 콘솔 `[SCHED]` 출력 → JSONL 변환 | ✅ |
| `metrics.py` | 스케줄링 메트릭 계산 (response/turnaround/waiting/throughput) | ✅ |
| `event_detector.py` | 런타임 이벤트 감지 (기아, 낮은 처리율, 과도한 선점) | ✅ |

**데이터 파이프라인 흐름:**
```
workloads/*.json → workload_summary.json → recommendation.json
→ guard_decision.json → trace_*.jsonl → metrics.json / runtime_events.json
```

> **미완성:** `scheduler_simulator.py`에 SJF/SRTF 호스트 시뮬레이션 추가 필요

---

### 3-3. GUI 대시보드 — React/Vite

#### `dashboard_live/` ✅ 완료 (메인 대시보드)

- React 18.3 + Vite 5.4 기반
- `outputs/live/` 데이터를 1초 주기로 폴링
- 데이터 없을 때 노란색 배너 경고 표시

| 컴포넌트 | 역할 |
|---------|------|
| `Header` | 데이터 소스, 버전, 마지막 업데이트, 폴링 상태 |
| `LLMRecommendation` | 알고리즘 추천 + 신뢰도 |
| `AlgorithmGuard` | Guard 검증 결과 |
| `EvaluationResult` | 메트릭 평가 판정 (SUCCESS/NEAR-SUCCESS/FAIL) |
| `LLMExplanation` | 자연어 트레이스 설명 |
| `MainGantt` | 프로세스 실행 Gantt 차트 |
| `ProcessLanes` | 프로세스 상태 타임라인 |
| `TraceStack` | 트레이스 이벤트 스택 뷰어 |
| `MetricVisualization` | 메트릭 차트 (응답시간, 처리율 등) |
| `AlgorithmComparison` | 알고리즘 간 메트릭 비교 |
| `WorkloadSummary` | 워크로드 요약 통계 |

```bash
cd dashboard_live && npm install && npm run dev  # → http://localhost:5174
```

#### `dashboard_test/` ✅ 완료 (UI 테스트 랩)

- 정적 fixture 데이터 사용 (라이브 데이터 불필요)
- `src/data/fixtures.js`에 6가지 시나리오 내장
- 컴포넌트 레이아웃·디자인 독립 검증용

```bash
cd dashboard_test && npm install && npm run dev  # → http://localhost:5173
```

#### `dashboard/` — Streamlit 대시보드 (레거시)

- Python Streamlit 기반, 더 이상 주요 개발 대상 아님

---

### 3-4. 파이프라인 자동화 (`scripts/`) ✅ 완료

| 스크립트 | 역할 |
|---------|------|
| `run_live_dashboard_pipeline.py` | 전체 파이프라인 실행: simulator → metrics → `dashboard_live/public/live-data/` 복사 → `manifest.json` 갱신 |
| `check_xv6_scheduler.sh` | xv6 커널 수정 검증 하네스 (빌드 + 선택적 QEMU 부팅) |

---

### 3-5. 워크로드 정의 (`workloads/`) ✅ 완료

| 파일 | 설명 |
|------|------|
| `interactive_heavy.json` | 짧은 대화형 + 긴 CPU 집약적 (MLFQ 추천) |
| `short_jobs.json` | 모두 짧은 CPU 버스트 (SJF 효과적) |
| `long_cpu_bound_first.json` | 긴 작업 먼저 도착 (Convoy Effect 위험) |
| `mixed_workload.json` | CPU/IO 균형 혼합 |
| `starvation_risk.json` | 높은 우선순위 CPU 집약 → 낮은 우선순위 기아 위험 |
| `priority_sensitive.json` | 우선순위 스케줄링에 민감한 워크로드 |

---

### 3-6. 문서 (`docs/`) ✅ 완료

| 파일 | 내용 |
|------|------|
| `architecture.md` | 시스템 아키텍처 (3단계, 컴포넌트 책임) |
| `trace_format.md` | 트레이스 이벤트 스키마 (ARRIVE, DISPATCH, PREEMPT, SLEEP, WAKEUP, EXIT, QUEUE_CHANGE, CORRECTION_APPLIED) |
| `data_format.md` | 전체 JSON 인터페이스 스키마 레퍼런스 |
| `evaluation_plan.md` | 메트릭 평가 기준 및 판정 규칙 |
| `dashboard_data_contract.md` | 대시보드 데이터 인터페이스 명세 |
| `demo_runbook.md` | 단계별 데모 실행 가이드 |
| `work_status_sjf_srtf.md` | SJF/SRTF 구현 현황 상세 |

---

## 4. 현재 출력 데이터 상태

### `outputs/live/` (최근 실행: 2026-05-24)
```
workload_summary.json   — 워크로드 분석 결과
recommendation.json     — LLM 추천 (알고리즘 + 신뢰도)
guard_decision.json     — Guard 검증 결과
trace_rr.jsonl          — RR 트레이스 (기준선)
trace_fcfs.jsonl        — FCFS 트레이스
trace_priority.jsonl    — Priority 트레이스
trace_mlfq.jsonl        — MLFQ 트레이스
trace_sjf.jsonl         — SJF 트레이스
trace_srtf.jsonl        — SRTF 트레이스
metrics.json            — 전체 메트릭 + 판정 결과
trace_explanation.json  — LLM 자연어 트레이스 설명
```

---

## 5. 미완료 항목 (TODO)

### 높은 우선순위

| 항목 | 담당 파일 | 내용 |
|------|---------|------|
| xv6 SJF/SRTF 커밋 | `xv6-riscv/kernel/` | QEMU 검증 완료, 미커밋 상태 |
| Algorithm Guard SJF/SRTF 지원 | `tools/algorithm_guard.py` | SJF/SRTF + `predictor_params` 파라미터 검증 추가 |
| LLM Advisor SJF/SRTF 스키마 | `tools/llm_advisor.py` | `recommendation.json`에 `predictor_params` 필드 추가 |

### 중간 우선순위

| 항목 | 담당 파일 | 내용 |
|------|---------|------|
| 호스트 시뮬레이터 SJF/SRTF | `tools/scheduler_simulator.py` | 지수 평균 예측 기반 SJF/SRTF 시뮬레이션 구현 |
| 버스트 예측 오류 메트릭 | `tools/metrics.py` | `avg_burst_prediction_error` 계산 추가 |
| 트레이스 predictor 메타데이터 | `docs/trace_format.md` | `burst_hint=null` 규칙 유지하면서 predictor 파라미터를 메타데이터로 포함 |

### 낮은 우선순위

| 항목 | 내용 |
|------|------|
| SRTF 즉시 선점 | 새 프로세스 도착 시 다음 timer tick이 아닌 즉시 선점 (현재는 아키텍처 문서 준수) |
| Runtime Correction Proposer | `runtime_events.json` → LLM → `correction.json` 파이프라인 미구현 |
| Trace Explainer (자동화) | LLM이 트레이스 + 메트릭 자동 설명 (`trace_explanation.json` 생성 자동화) |
| Feedback Rule Generator | FAIL 평가 시 `feedback_rules.md` 자동 생성 미구현 |

---

## 6. 실행 방법

```bash
# xv6 빌드 & 실행
cd xv6-riscv && make qemu

# 호스트 측 시뮬레이터 단독 실행
python3 tools/scheduler_simulator.py

# 전체 파이프라인 (시뮬레이터 → 메트릭 → 대시보드 데이터 갱신)
python3 scripts/run_live_dashboard_pipeline.py

# React 라이브 대시보드
cd dashboard_live && npm run dev   # http://localhost:5174

# React UI 테스트 랩
cd dashboard_test && npm run dev   # http://localhost:5173

# (레거시) Streamlit 대시보드
streamlit run dashboard/dashboard.py
```

---

## 7. 브랜치 & 커밋 이력

```
feature/live-dashboard-split  ← 현재 브랜치
  42840d1  refactor: remove dashboard-react, harden dashboard_live data status
  c95b264  feat: split dashboard into test/live apps and add UI testbed
  0ea91b9  Polish React dashboard: tick axis, metric glow, comparison accent, trace fade
  c88bba6  Add React/Vite observability dashboard and host-side tool pipeline
  3031767  Add prediction-based SJF and SRTF Scheduling Algorithms to xv6
  0b1903d  Add root .gitignore to prevent accidental credential commits
  f7d5267  Add xv6 scheduler harness and implement RR/FCFS/Priority/MLFQ
  9ffe526  Align feedback mode with new metrics.json + outputs/ schema
  d1e881e  Add Algorithm Guard, params field, and prompt feedback loop (Role B)
```

---

## 8. 핵심 규칙 요약

| 규칙 | 내용 |
|------|------|
| API 키 | `.env`에만 저장, 절대 커밋 금지 |
| 미래 버스트 누출 | 실제 미래 CPU 버스트 값을 LLM에 전달 금지 |
| 데이터 인터페이스 | 모든 모듈 간 인터페이스는 JSON 또는 JSONL |
| 용어 통일 | "policy" 사용 금지 — "Scheduling Algorithm"으로 통일 |
| RR 기준선 | 항상 RR 비교 기준선 유지 |
| 피드백 루프 | FAIL 평가 시에만 Feedback Rule Generator 실행 |
| 런타임 보정 | LLM은 매 timer tick마다 호출하지 않음; 이벤트 감지 시에만 |
