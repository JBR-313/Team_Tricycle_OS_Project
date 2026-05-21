# 작업 현황: 예측 기반 SJF / SRTF Scheduling Algorithm 구현

**작성일**: 2026-05-21  
**브랜치**: `feature/xv6-scheduler-harness`  
**상태**: 구현 및 QEMU 검증 완료 — 미커밋 (uncommitted)

---

## 1. 개요

Oracle SJF/SRTF(미래 CPU 버스트를 직접 참조)는 **절대 금지**이며, 본 구현은 지수 평균(exponential averaging)으로 예측된 버스트 값만을 사용하는 **예측 기반 SJF / SRTF**를 xv6 커널에 추가한다.

- LLM은 실행 전 predictor 파라미터(`alpha_percent`, `initial`, `min`, `max`)만 추천
- 커널은 이미 관측된 CPU 사용량(`cur_burst_run`)만으로 예측 갱신
- 실제 미래 버스트 값은 어디에도 저장·참조·출력하지 않음

---

## 2. 변경 파일 목록

| 파일 | 구분 | 변경 내용 요약 |
|---|---|---|
| `kernel/proc.h` | 수정 | `SCHED_SJF=4`, `SCHED_SRTF=5` 상수; `struct proc`에 예측 필드 3개 추가 |
| `kernel/proc.c` | 수정 | 전역 predictor 파라미터, 지수 평균 업데이트, `sched_sjf`, `sched_srtf`, predictor 공개 API, `scheduler()` switch 확장, `sleep`/`wakeup`/`yield` 갱신 |
| `kernel/trap.c` | 수정 | tick당 관측 CPU 사용량 누적(`cur_burst_run++`); SJF 비선점, SRTF 매 tick 선점 |
| `kernel/sysproc.c` | 수정 | `sys_setpredictor`(파라미터 검증 포함), `sys_getpredictor`; `sys_setscheduler` 상한 SRTF까지 확장 |
| `kernel/syscall.h` | 수정 | `SYS_setpredictor=26`, `SYS_getpredictor=27` 추가 |
| `kernel/syscall.c` | 수정 | extern 선언 및 디스패치 테이블 등록 |
| `kernel/defs.h` | 수정 | `set_predictor_params`, `get_predicted_burst` 커널 API 선언 |
| `user/user.h` | 수정 | `setpredictor`, `getpredictor` 유저 스텁 선언 |
| `user/usys.pl` | 수정 | `setpredictor`, `getpredictor` 유저 스텁 생성 항목 추가 |
| `user/schedtest.c` | 수정 | `sjf`, `srtf` 모드 인자 지원 추가 |
| `user/predtest.c` | **신규** | predictor + SJF/SRTF 전용 검증 테스트 |
| `xv6-riscv/Makefile` | 수정 | `$U/_predtest` UPROGS 등록 |

---

## 3. 추가된 `struct proc` 필드

```c
// kernel/proc.h
int predicted_burst;   // 다음 CPU 버스트 예측값 (지수 평균)
int cur_burst_run;     // 현재 버스트에서 이미 관측된 CPU tick 수
int ready_since_tick;  // RUNNABLE 진입 tick (SJF/SRTF tie-break)
```

- **`predicted_burst`**: 미래 버스트 예측치. 실제 미래 버스트 ≠ 이 값.
- **`cur_burst_run`**: 타이머 인터럽트로만 누적 (이미 소비한 CPU만 반영).
- **`ready_since_tick`**: wakeup / yield / allocproc 시 갱신.

`freeproc()`에서 세 필드 모두 0으로 초기화.

---

## 4. 추가된 시스템콜

| 번호 | 이름 | 시그니처 | 설명 |
|---|---|---|---|
| 26 | `setpredictor` | `(alpha, initial, min, max) → int` | LLM 추천 predictor 파라미터 적용. 검증 후 글로벌 `pred` 갱신. |
| 27 | `getpredictor` | `(pid) → int` | 해당 pid의 현재 `predicted_burst` 반환 (예측치, 누출 아님). |

### 파라미터 검증 규칙 (`sys_setpredictor`)

| 파라미터 | 유효 범위 |
|---|---|
| `alpha_percent` | 0 ≤ alpha ≤ 100 |
| `min_predicted_burst` | min ≥ 1 |
| `max_predicted_burst` | max ≥ min, max ≤ 100000 |
| `initial_predicted_burst` | initial ≥ 1 (범위 초과 시 clamp) |

기본값: `alpha=50, initial=10, min=1, max=100`

---

## 5. 스케줄러 동작

### 5.1 예측 기반 SJF (SCHED_SJF = 4)

- **비선점**: 선택된 프로세스는 블록(sleep/exit)까지 CPU 점유
- 선택 기준: RUNNABLE 중 `predicted_burst` 최소
- Tie-break: `ready_since_tick` 작은 순 → `pid` 작은 순
- trap.c: FCFS와 동일 — 타이머 인터럽트에서 yield 안 함

```c
// kernel/proc.c — sched_sjf()
// Phase1: 전체 proc 테이블 스캔, 최소 predicted_burst 선택
// Phase2: re-acquire + RUNNABLE 재확인 후 실행
```

### 5.2 예측 기반 SRTF (SCHED_SRTF = 5)

- **선점**: 매 timer tick이 스케줄링 시점 (trap.c에서 yield)
- 선택 기준: RUNNABLE 중 `predicted_remaining` 최소
  - `predicted_remaining = max(predicted_burst - cur_burst_run, min_predicted_burst)`
- Tie-break: `ready_since_tick` → `pid`
- **LLM은 스케줄링 루프 안에서 호출하지 않음**

### 5.3 지수 평균 예측 갱신

```
new_prediction = (alpha * last_observed_burst + (100 - alpha) * old_prediction) / 100
```

- 정수 연산만 사용
- 갱신 시점: `sleep()` 진입 직전 (CPU 버스트 종료 = I/O 블록 시점)
- 입력: `cur_burst_run` (이미 소비한 tick 수, 타이머로 누적)
- 결과는 `[min, max]`로 clamp

### 5.4 기존 Scheduling Algorithm과의 공존

| 모드 | 선점 방식 | 예측 필드 사용 |
|---|---|---|
| RR (0) | 매 tick | 아니오 |
| FCFS (1) | 없음 | 아니오 |
| Priority (2) | 매 tick | 아니오 |
| MLFQ (3) | quantum 소진 시 | 아니오 |
| **SJF (4)** | **없음** | **predicted_burst** |
| **SRTF (5)** | **매 tick** | **predicted_remaining** |

기존 알고리즘 코드는 변경하지 않음. `cur_burst_run`/`rtime` 누적은 전 모드에서 수행되나 SJF/SRTF에서만 의미 있음.

---

## 6. 미래 CPU 버스트 누출 방지

| 방지 항목 | 조치 |
|---|---|
| 실제 cpu_bursts 배열 LLM 전달 금지 | predictor 파라미터(4개 정수)만 syscall로 수신 |
| 실제 미래 버스트 struct proc 저장 금지 | `predicted_burst`, `cur_burst_run`만 저장 |
| 커널 내 워크로드 JSON 파싱 금지 | 커널은 파일 시스템 접근 안 함 |
| LLM 스케줄링 루프 호출 금지 | 예측 갱신은 순수 정수 연산 (`update_burst_prediction`) |
| 트레이스 출력 금지 | `sched_debug`에 burst 값 미포함; `burst_hint=null` 유지 |
| 커널에서 LLM 호출 금지 | predictor는 kernel-local 정수 연산 |

---

## 7. 검증 결과 (QEMU CPUS=1)

### 7.1 빌드
```
make fs.img → 오류·경고 없이 성공
```

### 7.2 `predtest` 실행 결과 요약

```
predtest: predictor params set (alpha=50 init=10 min=1 max=100)
predtest: --- SJF ---
predtest[sjf]: pid=4 round=0 predicted_burst=5    ← 초기 10에서 관측 후 갱신
predtest[sjf]: pid=5 round=1 predicted_burst=3    ← 추가 수렴
predtest[sjf]: pid=5 round=2 predicted_burst=2
predtest: --- SRTF ---
predtest[srtf]: pid=8 round=2 predicted_burst=2
predtest: done
```

- 잘못된 파라미터(alpha=150, min>max) → 거부(FAIL 메시지 없음)
- `predicted_burst`: 초기 10 → 관측값 수렴 (더 짧은 버스트 = 더 작은 값)
- SJF/SRTF 모두 모든 자식 완료, 셸 정상 복귀

### 7.3 기존 알고리즘 회귀 테스트

```
schedtest mlfq → 모든 자식 정상 완료
schedtest sjf  → 모든 자식 정상 완료
```

---

## 8. 미완료 / 추후 작업

| 항목 | 상태 | 비고 |
|---|---|---|
| 커밋 | **미완료** | 요청 없음 — 별도 커밋 필요 |
| Algorithm Guard SJF/SRTF 지원 | 미완료 | `tools/algorithm_guard.py`에 SJF/SRTF + predictor 파라미터 검증 추가 필요 |
| `recommendation.json` SJF/SRTF 스키마 | 미완료 | LLM advisor가 SJF/SRTF + predictor params 추천 가능하도록 확장 필요 |
| 트레이스 JSON 예측 메타데이터 | 미완료 | `burst_hint` 규칙 유지하면서 predictor 파라미터를 메타데이터로 포함 가능 |
| SRTF: 새 프로세스 도착 시 즉시 선점 | 미완료 | 현재는 다음 timer tick에 선점 (스케줄링 시점 기반, 아키텍처 문서 준수) |
| 호스트 측 `scheduler_simulator.py` SJF/SRTF | 미완료 | xv6와 동일 동작의 시뮬레이터 확장 필요 |
| `metrics.py` 버스트 예측 오류 계산 | 미완료 | 실행 후 `avg_burst_prediction_error` 계산 (`evaluation_plan.md` 참조) |
| 대시보드 SJF/SRTF 지원 | 미완료 | `dashboard.py` 알고리즘 목록 확장 필요 |

---

## 9. 관련 파일 (데이터 인터페이스)

CLAUDE.md 및 data_format.md의 인터페이스 규칙은 유지됨:

```
workloads/*.json
    ↓ (cpu_bursts LLM에 전달 안 함)
workload_summary.json
    ↓
recommendation.json  ← SJF/SRTF + predictor_params 추천 가능하도록 확장 필요
    ↓
guard_decision.json  ← algorithm_guard.py SJF/SRTF 지원 추가 필요
    ↓
xv6 실행 (SJF/SRTF, 예측 기반)
    ↓
trace.jsonl (burst_hint=null 유지)
    ↓
metrics.json (avg_burst_prediction_error 추가 필요)
```
