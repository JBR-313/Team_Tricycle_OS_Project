# LLM Sched Copilot — Architecture

## Overview

LLM Sched Copilot is an **LLM-for-OS** project.

The LLM acts as a scheduling decision support layer for xv6.  
The LLM recommends, corrects, and explains xv6 Scheduling Algorithms.  
xv6 executes the Scheduling Algorithm.  
Metrics verify the result.  
The GUI visualizes the process.

> **LLM suggests. Algorithm Guard checks. xv6 executes. Metrics verify. GUI explains.**

The LLM is **not** the scheduler. xv6 is the execution authority.

---

## System Principle

| Component | Responsibility |
|-----------|----------------|
| LLM | Interprets workload, recommends Scheduling Algorithm, proposes correction, explains result |
| Algorithm Guard | Validates every LLM output before it is applied |
| xv6 | Executes the selected Scheduling Algorithm |
| Scheduler Simulator | Development fallback when xv6 is not yet integrated |
| Scheduling Trace Collector | Collects Scheduling Trace Logs during execution |
| Trace Parser | Parses raw trace events into structured records |
| Metrics Evaluator | Calculates scheduling metrics from parsed trace |
| Event Detector | Detects scheduling problems at runtime |
| Runtime Correction Proposer | Requests LLM correction when a problem is detected |
| Trace Explainer | Generates natural-language explanation after execution |
| Feedback Rule Generator | Generates rules when LLM recommendation failed |
| GUI Observability Dashboard | Visualizes the whole process |

---

## Three Phases

### Phase 1 — Before Running

The system prepares the Scheduling Algorithm recommendation before xv6 starts.

```
workloads/*.json
    ↓
Workload Analyzer
    ↓  workload_summary.json
LLM Workload Interpreter
    ↓  workload interpretation
LLM Scheduling Algorithm Advisor
    ↓  recommendation.json
Algorithm Guard
    ↓  guard_decision.json
```

**Workload Analyzer** reads the workload definition and produces a summary of observable characteristics: process count, CPU-bound tendency, arrival pattern, burst variance, and priority distribution.

**LLM Workload Interpreter** reads the summary and infers workload type, main risks, and target metric. It does not know actual future execution results.

**LLM Scheduling Algorithm Advisor** recommends a Scheduling Algorithm and parameters based on the interpretation. The recommendation is sent to Algorithm Guard before execution.

**Algorithm Guard** validates the recommendation: checks whether the Scheduling Algorithm is implemented, parameters are in valid ranges, and the JSON schema is correct. It accepts, warns, or rejects. A rejected recommendation falls back to a safe Scheduling Algorithm.

---

### Phase 2 — Running

xv6 (or the Simulator) executes the Scheduling Algorithm and emits a Scheduling Trace Log.

```
guard_decision.json
    ↓
xv6 Scheduling Algorithm Execution  (or Scheduler Simulator)
    ↓  trace.jsonl
Scheduling Trace Collector
    ↓
Trace Parser
    ↓  parsed records
Metrics Evaluator          Event Detector
    ↓  metrics.json              ↓  runtime_events.json
                        Runtime Correction Proposer
                            ↓  correction.json → Algorithm Guard → host-side re-run → correction_applied.json
```

**xv6 Scheduling Algorithm Execution** is the final target. The kernel executes the Scheduling Algorithm received from Algorithm Guard.

**Scheduler Simulator** is the development fallback. It simulates the same Scheduling Algorithm on the host side and emits trace.jsonl in the same format.

**Scheduling Trace Collector** records scheduling events (ARRIVE, DISPATCH, PREEMPT, SLEEP, WAKEUP, EXIT, QUEUE_CHANGE, CORRECTION_APPLIED) as JSON Lines.

**Trace Parser** reads trace.jsonl and produces structured records for downstream consumers.

**Metrics Evaluator** calculates response time, turnaround time, waiting time, throughput, and other metrics.

**Event Detector** watches the trace for scheduling problems: starvation, poor response time, long CPU-bound domination, high waiting time.

**Runtime Correction Proposer** summarizes the detected event and asks the LLM for a correction. The correction is validated by Algorithm Guard. It is applied as a host-side post-evaluation re-run (a second xv6 run with the corrected algorithm), not injected mid-run inside the kernel. The LLM is not called at every timer tick.

---

### Phase 3 — After Running

After execution ends, the system explains the result and generates feedback.

```
trace.jsonl + metrics.json
    ↓
Trace Explainer
    ↓  trace_explanation.json
GUI Observability Dashboard

metrics.json (if FAIL)
    ↓
Feedback Rule Generator
    ↓  feedback_rules.md
LLM Scheduling Algorithm Advisor  (next run)
```

**Trace Explainer** receives a summary of the Scheduling Trace Log, metrics, and detected events. It generates a natural-language explanation: what happened, why it happened, and what could be improved.

**Feedback Rule Generator** runs only when the LLM recommendation failed. It generates a feedback rule that is injected into the next LLM prompt.

**GUI Observability Dashboard** visualizes the whole process: workload summary, recommendation, guard result, live or replayed Scheduling Trace Log, Gantt chart, ready queue timeline, process state table, runtime correction events, before/after metrics, trace explanation, and feedback rules.

---

## Supported Scheduling Algorithms

| Algorithm | Notes |
|-----------|-------|
| Round Robin | Default and baseline. Must be preserved for comparison. |
| FCFS | Simple arrival-order scheduling. Subject to convoy effect. |
| Priority + Aging | Priority scheduling with aging to prevent starvation. |
| MLFQ | Multiple queues with different time quantums. LLM can suggest parameters. |
| SJF / SRTF | Requires burst predictor. Future CPU bursts must not be given to LLM as input. |

---

## Limitations

- The LLM is not called at every timer tick.
- The LLM does not directly choose the next process.
- The LLM does not directly modify xv6 kernel state.
- Runtime correction is applied only after validation by Algorithm Guard.
- Runtime correction takes effect as a host-side post-evaluation re-run, not mid-run inside the kernel.
- Future CPU bursts are not given to the LLM as input.

---

## Data Interface Rules

- All module-to-module interfaces use JSON or JSON Lines (JSONL).
- Do not use "policy" — use "Scheduling Algorithm" consistently.
- API keys must be stored in `.env` only. Never commit `.env` to Git.

---

---

## 아키텍처 개요 (한글)

LLM Sched Copilot은 **LLM-for-OS** 프로젝트입니다.

LLM은 xv6 CPU 스케줄링을 위한 의사결정 지원 계층으로 작동합니다.  
LLM은 xv6 스케줄링 알고리즘을 추천하고, 보정하며, 설명합니다.  
xv6가 스케줄링 알고리즘을 실행합니다.  
메트릭이 결과를 검증합니다.  
GUI가 전체 과정을 시각화합니다.

LLM은 스케줄러가 아닙니다. xv6가 실행 권한을 갖습니다.

### 3단계 구조

**실행 전 (Before Running)**  
워크로드 정의 → 워크로드 분석기 → LLM 워크로드 인터프리터 → LLM 스케줄링 알고리즘 어드바이저 → 알고리즘 가드

**실행 중 (Running)**  
알고리즘 가드 → [xv6 스케줄링 알고리즘 실행 | 스케줄러 시뮬레이터] → 스케줄링 트레이스 수집기 → 트레이스 파서 → 메트릭 평가기 + 이벤트 감지기 → 런타임 보정 제안기

**실행 후 (After Running)**  
트레이스 설명기 → 피드백 규칙 생성기 → GUI 관측 대시보드

### 핵심 설계 규칙

- LLM은 스케줄러가 아니다. `recommendation.json`과 `correction.json`만 출력한다.
- xv6가 실행 권한을 갖는다. 모든 스케줄링 알고리즘 실행은 xv6 또는 시뮬레이터에서 이루어진다.
- 알고리즘 가드는 LLM의 모든 출력을 적용 전에 검증한다.
- 런타임 보정은 다음 스케줄링 시점에 적용된다.
- 미래 CPU 버스트는 LLM에게 입력으로 제공하지 않는다.
- 피드백 루프는 FAIL 평가 시에만 동작한다.
- RR 베이스라인은 항상 비교 기준으로 보존한다.
- API 키는 `.env`에만 저장하고 절대 Git에 커밋하지 않는다.
- 모든 모듈 인터페이스는 JSON 또는 JSONL을 사용한다.
- "policy" 대신 "Scheduling Algorithm(스케줄링 알고리즘)"을 일관되게 사용한다.
