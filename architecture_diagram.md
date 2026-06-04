# LLM Sched Copilot — Architecture Diagram

---

## ─── ENGLISH VERSION ───────────────────────────────────────────────────────

### 1. Three-Phase Execution Flow

```mermaid
flowchart TD
    subgraph BEFORE ["⬛ BEFORE RUNNING"]
        direction TB
        B0["📁 Workload Definition
        workloads/*.json"]

        B1["🔍 Workload Analyzer
        tools/workload_analyzer.py
        ─────────────────
        Summarizes observable workload characteristics"]

        B2["🧠 LLM Workload Interpreter
        tools/llm_advisor.py · Solar Pro 3 API
        ─────────────────
        Infers workload type, risks, target metric"]

        B3["🤖 LLM Scheduling Algorithm Advisor
        tools/llm_advisor.py · Solar Pro 3 API
        ─────────────────
        Recommends Scheduling Algorithm + parameters"]

        B4["🛡️ Algorithm Guard
        tools/algorithm_guard.py
        ─────────────────
        Validates LLM output — accept / warn / reject"]

        B0 --> B1
        B1 -->|"workload_summary.json"| B2
        B2 -->|"workload_interpretation"| B3
        B3 -->|"recommendation.json"| B4
    end

    subgraph RUNNING ["🟩 RUNNING"]
        direction TB
        R0A["⚙️ xv6 Scheduling Algorithm Execution
        xv6-riscv/kernel/
        ─────────────────
        Final target · RR · FCFS · Priority · MLFQ"]

        R0B["🖥️ Scheduler Simulator
        tools/scheduler_simulator.py
        ─────────────────
        Development fallback · host-side simulation"]

        R1["📋 Scheduling Trace Collector
        built into xv6 / simulator
        ─────────────────
        ARRIVE · DISPATCH · PREEMPT · SLEEP · WAKEUP · EXIT"]

        R2["🔎 Trace Parser
        tools/trace_parser.py
        ─────────────────
        Parses trace.jsonl into structured records"]

        R3["📊 Metrics Evaluator
        tools/metrics.py
        ─────────────────
        WT · RT · TAT · Throughput · Starvation · Preemptions"]

        R4["🚨 Event Detector
        tools/event_detector.py
        ─────────────────
        Starvation · Poor RT · Long CPU-bound domination"]

        R5["🔄 Runtime Correction Proposer
        tools/runtime_correction.py · LLM
        ─────────────────
        Proposes correction → Algorithm Guard → Next Scheduling Point"]

        R0A -->|"trace.jsonl"| R1
        R0B -->|"trace.jsonl"| R1
        R1  -->|"trace.jsonl"| R2
        R2  -->|"parsed records"| R3
        R2  -->|"parsed records"| R4
        R4  -->|"runtime_events.json"| R5
        R5  -->|"correction.json → Guard → next scheduling point"| R0A
        R5  -->|"correction.json → Guard → next scheduling point"| R0B
    end

    subgraph AFTER ["🟦 AFTER RUNNING"]
        direction TB
        A1["💬 Trace Explainer
        tools/trace_explainer.py · LLM
        ─────────────────
        Natural-language explanation of trace + metrics"]

        A2["📝 Feedback Rule Generator
        tools/feedback_generator.py · LLM
        ─────────────────
        Generates rules when LLM recommendation failed"]

        A3["🖼️ GUI Observability Dashboard
        dashboard_live (React)
        ─────────────────
        Gantt · Queue · Metrics · Correction · Explanation"]

        A1 --> A3
        A2 --> A3
        A2 -.->|"feedback_rules.md · next run"| B3
    end

    B4 -->|"guard_decision.json ✓"| R0A
    B4 -->|"guard_decision.json ✓"| R0B
    R3 -->|"metrics.json"| A1
    R3 -->|"metrics.json"| A2
    R3 -->|"metrics.json"| A3
    R1 -->|"trace.jsonl"| A1
    R1 -->|"trace.jsonl"| A3
    R4 -->|"runtime_events.json"| A3

    classDef before fill:#E6F1FB,stroke:#185FA5,color:#0C447C
    classDef running fill:#E1F5EE,stroke:#0F6E56,color:#085041
    classDef after  fill:#EEEDFE,stroke:#534AB7,color:#3C3489

    class B0,B1,B2,B3,B4 before
    class R0A,R0B,R1,R2,R3,R4,R5 running
    class A1,A2,A3 after
```

---

### 2. Module Interaction — File I/O

```mermaid
flowchart LR

subgraph INPUT["📂 Input"]
    WJ["workloads/*.json"]
end

subgraph BEFORE_TOOLS["⬛ Before Running"]
    WA["workload_analyzer.py"]
    LI["llm_advisor.py (Interpreter)"]
    LA["llm_advisor.py (Advisor)"]
    AG["algorithm_guard.py"]
end

subgraph RUNNING_TOOLS["🟩 Running"]
    XV["xv6 Scheduling Algorithm Execution"]
    SS["scheduler_simulator.py"]
    TP["trace_parser.py"]
    ME["metrics.py"]
    ED["event_detector.py"]
    RC["runtime_correction.py"]
end

subgraph AFTER_TOOLS["🟦 After Running"]
    TE["trace_explainer.py"]
    FG["feedback_generator.py"]
    DB["dashboard.py"]
end

subgraph FILES["📄 Data Files"]
    WS["workload_summary.json"]
    REC["recommendation.json"]
    GD["guard_decision.json"]
    TR["trace.jsonl"]
    MT["metrics.json"]
    RE["runtime_events.json"]
    COR["correction.json"]
    TEX["trace_explanation.json"]
    FB["feedback_rules.md"]
end

WJ --> WA
WA --> WS

WS --> LI
LI --> LA
LA --> REC

REC --> AG
AG --> GD

GD --> XV
GD --> SS

XV --> TR
SS --> TR

TR --> TP

TP --> ME
TP --> ED

ME --> MT
ED --> RE

RE --> RC
RC --> COR

COR --> XV
COR --> SS

TR --> TE
MT --> TE

MT --> FG

TE --> TEX
FG --> FB

FB -.-> LA

TR --> DB
MT --> DB
REC --> DB
RE --> DB
TEX --> DB
FB --> DB

classDef before fill:#E6F1FB,stroke:#185FA5
classDef running fill:#E1F5EE,stroke:#0F6E56
classDef after fill:#EEEDFE,stroke:#534AB7
classDef data fill:#F1EFE8,stroke:#888780

class WA,LI,LA,AG before
class XV,SS,TP,ME,ED,RC running
class TE,FG,DB after
class WS,REC,GD,TR,MT,RE,COR,TEX,FB data
```

---

### 3. Data Format Reference

| File | Format | Producer | Consumer |
|------|--------|----------|----------|
| `workloads/*.json` | JSON array | Manual | `workload_analyzer.py` |
| `workload_summary.json` | JSON object | `workload_analyzer.py` | `llm_advisor.py` |
| `recommendation.json` | JSON object | `llm_advisor.py` | `algorithm_guard.py`, dashboard |
| `guard_decision.json` | JSON object | `algorithm_guard.py` | xv6 / `scheduler_simulator.py` |
| `trace.jsonl` | JSON Lines | xv6 / `scheduler_simulator.py` | `trace_parser.py`, `trace_explainer.py`, dashboard |
| `metrics.json` | JSON object | `metrics.py` | `trace_explainer.py`, `feedback_generator.py`, dashboard |
| `runtime_events.json` | JSON object | `event_detector.py` | `runtime_correction.py`, dashboard |
| `correction.json` | JSON object | `runtime_correction.py` | `algorithm_guard.py` → xv6 / simulator |
| `trace_explanation.json` | JSON object | `trace_explainer.py` | dashboard |
| `feedback_rules.md` | Markdown | `feedback_generator.py` | `llm_advisor.py` (next run, fail only) |

---

### 4. Phase Legend

| Phase | Color | Modules |
|-------|-------|---------|
| **Before Running** | Blue | Workload Analyzer · LLM Workload Interpreter · LLM Scheduling Algorithm Advisor · Algorithm Guard |
| **Running** | Teal | xv6 Scheduling Algorithm Execution · Scheduler Simulator · Trace Collector · Trace Parser · Metrics Evaluator · Event Detector · Runtime Correction Proposer |
| **After Running** | Purple | Trace Explainer · Feedback Rule Generator · GUI Observability Dashboard |

---

### 5. Metric Definitions

```
response_time   = first_run_time − arrival_time
turnaround_time = finish_time − arrival_time
waiting_time    = turnaround_time − total_cpu_burst_time
throughput      = completed_process_count / total_execution_time
```

---

### 6. Key Design Rules

- **LLM is not the scheduler.** It outputs `recommendation.json` and `correction.json` only.
- **xv6 is the execution authority.** All Scheduling Algorithm execution happens inside xv6 (or the simulator as a fallback).
- **Algorithm Guard** validates every LLM output — recommendation and runtime correction — before it is applied.
- **Runtime correction** is applied from the next scheduling point, not mid-tick.
- **Future CPU bursts** must not be given to the LLM as input.
- **Feedback loop** fires only on `FAIL` evaluation.
- **RR baseline** must always be preserved as a comparison reference.
- **API key** lives in `.env` only — never committed to Git.
- **All module interfaces** use JSON or JSON Lines (JSONL). Do not use CSV for new interfaces.

---

### 7. One-Line Summary

> **LLM suggests. Algorithm Guard checks. xv6 executes. Metrics verify. GUI explains.**

---
---

## ─── 한글 버전 ──────────────────────────────────────────────────────────────

### 1. 3단계 실행 흐름

```mermaid
flowchart TD
    subgraph BEFORE ["⬛ 실행 전 (BEFORE RUNNING)"]
        direction TB
        B0["📁 워크로드 정의
        workloads/*.json"]

        B1["🔍 워크로드 분석기
        tools/workload_analyzer.py
        ─────────────────
        관찰 가능한 워크로드 특성을 요약"]

        B2["🧠 LLM 워크로드 인터프리터
        tools/llm_advisor.py · Solar Pro 3 API
        ─────────────────
        워크로드 유형 · 위험 · 목표 메트릭 추론"]

        B3["🤖 LLM 스케줄링 알고리즘 어드바이저
        tools/llm_advisor.py · Solar Pro 3 API
        ─────────────────
        스케줄링 알고리즘 + 파라미터 추천"]

        B4["🛡️ 알고리즘 가드
        tools/algorithm_guard.py
        ─────────────────
        LLM 출력 검증 — 수락 / 경고 / 거부"]

        B0 --> B1
        B1 -->|"workload_summary.json"| B2
        B2 -->|"워크로드 해석"| B3
        B3 -->|"recommendation.json"| B4
    end

    subgraph RUNNING ["🟩 실행 중 (RUNNING)"]
        direction TB
        R0A["⚙️ xv6 스케줄링 알고리즘 실행
        xv6-riscv/kernel/
        ─────────────────
        최종 목표 · RR · FCFS · Priority · MLFQ"]

        R0B["🖥️ 스케줄러 시뮬레이터
        tools/scheduler_simulator.py
        ─────────────────
        개발 대체 경로 · 호스트 측 시뮬레이션"]

        R1["📋 스케줄링 트레이스 수집기
        xv6 내장 / 시뮬레이터
        ─────────────────
        ARRIVE · DISPATCH · PREEMPT · SLEEP · WAKEUP · EXIT"]

        R2["🔎 트레이스 파서
        tools/trace_parser.py
        ─────────────────
        trace.jsonl을 구조화된 레코드로 파싱"]

        R3["📊 메트릭 평가기
        tools/metrics.py
        ─────────────────
        WT · RT · TAT · 처리량 · 기아 · 선점 횟수"]

        R4["🚨 이벤트 감지기
        tools/event_detector.py
        ─────────────────
        기아 · 응답 시간 불량 · CPU 독점 감지"]

        R5["🔄 런타임 보정 제안기
        tools/runtime_correction.py · LLM
        ─────────────────
        보정 제안 → 알고리즘 가드 → Next Scheduling Point 적용"]

        R0A -->|"trace.jsonl"| R1
        R0B -->|"trace.jsonl"| R1
        R1  -->|"trace.jsonl"| R2
        R2  -->|"파싱된 레코드"| R3
        R2  -->|"파싱된 레코드"| R4
        R4  -->|"runtime_events.json"| R5
        R5  -->|"correction.json → 가드 → 다음 스케줄링 시점"| R0A
        R5  -->|"correction.json → 가드 → 다음 스케줄링 시점"| R0B
    end

    subgraph AFTER ["🟦 실행 후 (AFTER RUNNING)"]
        direction TB
        A1["💬 트레이스 설명기
        tools/trace_explainer.py · LLM
        ─────────────────
        트레이스 + 메트릭을 자연어로 설명"]

        A2["📝 피드백 규칙 생성기
        tools/feedback_generator.py · LLM
        ─────────────────
        LLM 추천 실패 시 규칙 생성"]

        A3["🖼️ GUI 관측 대시보드
        dashboard_live (React)
        ─────────────────
        Gantt · 큐 · 메트릭 · 보정 · 설명"]

        A1 --> A3
        A2 --> A3
        A2 -.->|"feedback_rules.md · 다음 실행"| B3
    end

    B4 -->|"guard_decision.json ✓"| R0A
    B4 -->|"guard_decision.json ✓"| R0B
    R3 -->|"metrics.json"| A1
    R3 -->|"metrics.json"| A2
    R3 -->|"metrics.json"| A3
    R1 -->|"trace.jsonl"| A1
    R1 -->|"trace.jsonl"| A3
    R4 -->|"runtime_events.json"| A3

    classDef before fill:#E6F1FB,stroke:#185FA5,color:#0C447C
    classDef running fill:#E1F5EE,stroke:#0F6E56,color:#085041
    classDef after  fill:#EEEDFE,stroke:#534AB7,color:#3C3489

    class B0,B1,B2,B3,B4 before
    class R0A,R0B,R1,R2,R3,R4,R5 running
    class A1,A2,A3 after
```

---

### 2. 데이터 형식 레퍼런스

| 파일 | 형식 | 생성 모듈 | 소비 모듈 |
|------|------|-----------|-----------|
| `workloads/*.json` | JSON 배열 | 수동 | `workload_analyzer.py` |
| `workload_summary.json` | JSON 객체 | `workload_analyzer.py` | `llm_advisor.py` |
| `recommendation.json` | JSON 객체 | `llm_advisor.py` | `algorithm_guard.py`, 대시보드 |
| `guard_decision.json` | JSON 객체 | `algorithm_guard.py` | xv6 / `scheduler_simulator.py` |
| `trace.jsonl` | JSON Lines | xv6 / `scheduler_simulator.py` | `trace_parser.py`, `trace_explainer.py`, 대시보드 |
| `metrics.json` | JSON 객체 | `metrics.py` | `trace_explainer.py`, `feedback_generator.py`, 대시보드 |
| `runtime_events.json` | JSON 객체 | `event_detector.py` | `runtime_correction.py`, 대시보드 |
| `correction.json` | JSON 객체 | `runtime_correction.py` | `algorithm_guard.py` → xv6 / 시뮬레이터 |
| `trace_explanation.json` | JSON 객체 | `trace_explainer.py` | 대시보드 |
| `feedback_rules.md` | 마크다운 | `feedback_generator.py` | `llm_advisor.py` (다음 실행, fail 시에만) |

---

### 3. 단계별 범례

| 단계 | 색상 | 모듈 |
|------|------|------|
| **실행 전** | 파란색 | 워크로드 분석기 · LLM 워크로드 인터프리터 · LLM 스케줄링 알고리즘 어드바이저 · 알고리즘 가드 |
| **실행 중** | 청록색 | xv6 스케줄링 알고리즘 실행 · 스케줄러 시뮬레이터 · 트레이스 수집기 · 트레이스 파서 · 메트릭 평가기 · 이벤트 감지기 · 런타임 보정 제안기 |
| **실행 후** | 보라색 | 트레이스 설명기 · 피드백 규칙 생성기 · GUI 관측 대시보드 |

---

### 4. 메트릭 정의

```
응답 시간 (response_time)   = first_run_time − arrival_time
반환 시간 (turnaround_time) = finish_time − arrival_time
대기 시간 (waiting_time)    = turnaround_time − total_cpu_burst_time
처리량   (throughput)       = 완료된 프로세스 수 / 전체 실행 시간
```

---

### 5. 핵심 설계 규칙

- **LLM은 스케줄러가 아니다.** `recommendation.json`과 `correction.json`만 출력한다.
- **xv6가 실행 권한을 갖는다.** 모든 스케줄링 알고리즘 실행은 xv6(또는 시뮬레이터)에서 이루어진다.
- **알고리즘 가드**는 LLM의 모든 출력(추천 및 런타임 보정)을 적용 전 검증한다.
- **런타임 보정**은 다음 스케줄링 시점에 적용된다. 매 타이머 틱마다 LLM을 호출하지 않는다.
- **미래 CPU 버스트**는 LLM에게 입력으로 제공하지 않는다.
- **피드백 루프**는 `FAIL` 평가 시에만 동작한다.
- **RR 베이스라인**은 항상 비교 기준으로 보존되어야 한다.
- **API 키**는 `.env`에만 저장하고 절대 Git에 커밋하지 않는다.
- **모든 모듈 인터페이스**는 JSON 또는 JSON Lines(JSONL)를 사용한다.

---

### 6. 한 줄 요약

> **LLM이 제안한다. 알고리즘 가드가 검증한다. xv6가 실행한다. 메트릭이 검증한다. GUI가 설명한다.**
