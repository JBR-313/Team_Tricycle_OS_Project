3조 Tricycle

# xv6 Tutor

**LLM-Assisted Visual Tutor for OS Scheduling**

## 1. Project Summary

xv6SchedTutor is an educational **LLM for OS** project that helps students understand operating-system scheduling through visualized xv6-style process state transitions.

Instead of building a production-level scheduler, this project focuses on making invisible scheduling behavior visible and explainable. The system visualizes process states, ready queues, CPU allocation, preemption, completion, and scheduling metrics. An LLM is used as a tutor that explains scheduling traces, diagnoses performance issues, and suggests what-if scheduling experiments.

The LLM is **not** the main controller of the operating system. It acts as an advisory tool. Actual scheduling decisions are simulated and evaluated by our deterministic scheduler and evaluator.

---

## 2. Motivation

Students often learn xv6 scheduling through source code, terminal outputs, and simple logs. However, scheduling is inherently dynamic and difficult to understand from text alone.

For example:

- Processes move between states such as `RUNNABLE`, `RUNNING`, `SLEEPING`, and `TERMINATED`.
- The ready queue changes over time.
- Timer interrupts may cause preemption.
- Different scheduling policies produce different waiting times, response times, and turnaround times.
- Problems such as convoy effect, starvation, and unfair CPU allocation are hard to observe directly.

This project aims to help students observe, understand, and experiment with xv6-style scheduling behavior.

---

## 3. Project Direction

This project follows:

> **Direction B — LLM for OS**

The LLM is integrated into an operating-system learning tool. It receives scheduling traces and performance metrics, then provides explanations and policy suggestions.

The actual OS-style scheduling logic is implemented by our own simulator and evaluator.

---

## 4. Core Idea

The system works as follows:

```text
xv6-style Workload
        ↓
Scheduler Simulator
        ↓
Event Trace Generator
        ↓
Visual Scheduler Timeline
        ↓
Metrics Collector
        ↓
LLM Tutor / Advisor
        ↓
What-if Scheduling Experiment
        ↓
Evaluator
```

The LLM explains why a process waited, why response time increased, why starvation occurred, or why another scheduling policy might be better.

However, LLM suggestions are accepted only when they satisfy predefined evaluation conditions.

---

## 5. Main Features

### 5.1 xv6-style Scheduling Simulator

The simulator models basic xv6-style processes and scheduling behavior.

Each process contains:

```text
pid
arrival_time
burst_time
remaining_time
priority
state
waiting_time
response_time
turnaround_time
```

Supported or planned scheduling algorithms:

- FCFS
- Round Robin
- Priority Scheduling
- MLFQ

---

### 5.2 Event Trace Generator

The simulator generates structured event traces.

Example:

```json
[
  {
    "time": 0,
    "event": "ARRIVE",
    "pid": 1,
    "state": "RUNNABLE"
  },
  {
    "time": 1,
    "event": "DISPATCH",
    "pid": 1,
    "state": "RUNNING"
  },
  {
    "time": 5,
    "event": "PREEMPT",
    "pid": 1,
    "state": "RUNNABLE"
  },
  {
    "time": 10,
    "event": "EXIT",
    "pid": 1,
    "state": "TERMINATED"
  }
]
```

These traces are used both for visualization and LLM-based explanation.

---

### 5.3 Visual Scheduler Timeline

The GUI visualizes the scheduling process.

Planned visualization components:

- Process table
- Ready queue
- CPU execution box
- Sleeping/waiting process list
- Gantt chart
- Scheduling metrics panel

The goal is to help students understand how scheduler decisions affect process behavior over time.

---

### 5.4 LLM Tutor

The LLM explains scheduling behavior based on the trace and metrics.

Example questions the LLM can answer:

- Why did process P2 wait so long?
- Why did FCFS cause high waiting time?
- Why does Round Robin improve response time?
- What is the convoy effect in this trace?
- Why can priority scheduling cause starvation?
- How does aging solve starvation?

---

### 5.5 What-if Scheduling Advisor

The LLM can suggest scheduling experiments.

Example:

```json
{
  "diagnosis": "Short interactive processes are delayed by a long CPU-bound process.",
  "suggestion": {
    "algorithm": "Round Robin",
    "time_quantum": 4
  },
  "expected_effect": "Response time may improve because CPU time is distributed more frequently."
}
```

The system then runs the suggested policy and compares the result with the baseline.

---

### 5.6 Metric-based Evaluator

LLM suggestions are not blindly accepted.

A suggested policy is accepted only if it satisfies conditions such as:

- Average response time improves.
- Average waiting time does not significantly worsen.
- Starvation does not occur.
- All processes eventually terminate.
- Scheduling parameters are within valid ranges.

Example result:

```json
{
  "baseline": "FCFS",
  "suggested_policy": "Round Robin, quantum = 4",
  "accepted": true,
  "reason": {
    "avg_response_time": "12.0 -> 4.2",
    "avg_waiting_time": "18.3 -> 13.1",
    "starvation": false
  }
}
```

---

## 6. OS Concepts Used

This project directly uses the following operating-system concepts:

### Process

The system models each process with a PID, state, burst time, priority, and scheduling-related metrics.

### Process State

The simulator visualizes state transitions such as:

```text
NEW → RUNNABLE → RUNNING → SLEEPING → RUNNABLE → TERMINATED
```

### CPU Scheduling

The project compares multiple scheduling algorithms:

- FCFS
- Round Robin
- Priority Scheduling
- MLFQ

### Ready Queue

The ready queue is visualized to show which processes are waiting for CPU allocation.

### Preemption

Round Robin and MLFQ demonstrate preemptive scheduling behavior.

### Starvation and Aging

Priority scheduling and MLFQ scenarios can demonstrate starvation and aging-based mitigation.

### Scheduling Metrics

The system calculates:

- Waiting time
- Turnaround time
- Response time
- Throughput
- Starvation occurrence

---

## 7. LLM Role

The LLM is used as:

```text
Tutor
Trace Explainer
Misconception Corrector
Scheduling Advisor
What-if Experiment Recommender
```

The LLM is not used as:

```text
Kernel Controller
Direct Scheduler
Context-switch Decision Maker
Unverified Policy Executor
```

This design keeps the OS logic deterministic while using the LLM to improve explanation, analysis, and learning support.

---

## 8. Tech Stack

Planned stack:

```text
Language: Python
LLM Backend: Upstage Solar Pro 3 API
Visualization: Streamlit or React
Scheduler Core: Custom Python simulator
Data Format: JSON event traces
Version Control: GitHub
```

Possible optional components:

```text
xv6 trace integration
Graph visualization
Gantt chart rendering
Scenario presets
```

---

## 9. Demo Scenarios

### Scenario 1: FCFS Convoy Effect

A long CPU-bound process arrives before several short interactive processes.

Expected learning point:

```text
FCFS can cause short jobs to wait behind a long job, increasing average waiting time.
```

---

### Scenario 2: Round Robin Quantum Trade-off

The same workload is tested with different time quantum values.

Expected learning point:

```text
A large quantum behaves like FCFS, while a very small quantum may increase context-switch overhead.
```

---

### Scenario 3: Priority Scheduling and Starvation

Low-priority processes wait too long because high-priority processes dominate the CPU.

Expected learning point:

```text
Priority scheduling can cause starvation, and aging can mitigate it.
```

---

### Scenario 4: LLM-assisted Policy Suggestion

The LLM analyzes the trace and suggests a new scheduling policy.

Expected learning point:

```text
Scheduling policies should be evaluated using metrics instead of being accepted blindly.
```

---

## 10. Evaluation Plan

We will evaluate the project using both scheduling correctness and educational usefulness.

### Scheduling Metrics

- Average waiting time
- Average turnaround time
- Average response time
- Throughput
- Starvation occurrence

### LLM Advisor Evaluation

- Whether the explanation matches the actual trace
- Whether the suggested policy is valid
- Whether the suggested policy improves metrics
- Whether the system correctly accepts or rejects the suggestion

### Visualization Evaluation

- Whether the GUI matches the event trace
- Whether process state transitions are shown correctly
- Whether the Gantt chart matches scheduler output

---

## 11. Project Milestones

### Week 10

- Define project topic
- Write problem statement
- Design system architecture
- Define OS concepts and core features

### Week 11

- Implement basic scheduler simulator
- Implement FCFS and Round Robin
- Generate event traces
- Calculate basic scheduling metrics

### Week 12

- Add Priority Scheduling and MLFQ
- Build initial visualizer
- Connect Solar API
- Implement LLM trace explanation

### Week 13

- Add what-if policy advisor
- Implement evaluator
- Prepare demo scenarios
- Run evaluation experiments
- Draft technical report and presentation

### Week 14

- Finalize application
- Finalize report
- Finalize English presentation slides
- Final demo

---

## 12. How to Run

> This section will be updated as implementation progresses.

Example:

```bash
git clone <repository-url>
cd <repository-name>
pip install -r requirements.txt
streamlit run app.py
```

Environment variables:

```bash
UPSTAGE_API_KEY=your_api_key_here
```

Do not commit API keys to GitHub.

---

## 13. Repository Structure

Planned structure:

```text
.
├── README.md
├── README_ko.md
├── requirements.txt
├── app.py
├── src/
│   ├── scheduler/
│   │   ├── fcfs.py
│   │   ├── round_robin.py
│   │   ├── priority.py
│   │   └── mlfq.py
│   ├── trace/
│   │   └── event_logger.py
│   ├── llm/
│   │   └── advisor.py
│   ├── evaluator/
│   │   └── metrics.py
│   └── visualization/
│       └── dashboard.py
├── scenarios/
│   ├── convoy_effect.json
│   ├── rr_quantum_tradeoff.json
│   └── priority_starvation.json
├── docs/
│   ├── architecture.md
│   ├── development_process.md
│   └── report.md
└── assets/
    └── demo/
```

---

## 14. Team Roles

> To be updated.

| Role | Responsibility | Member |
|---|---|---|
| Project Lead / Architecture | Overall design, GitHub management, report structure | TBD |
| Scheduler Core | Scheduling simulator, metrics, evaluator | TBD |
| LLM Integration | Solar API, prompt design, advisor output format | TBD |
| Visualization / Documentation | GUI, demo scenarios, README, slides | TBD |

---

## 15. Current Status

- Project direction selected: **LLM for OS**
- Main topic: **Educational xv6-style scheduling tutor**
- Initial README drafted
- Implementation will begin with scheduling simulator and event trace generation


# xv6 Tutor

**LLM 기반 운영체제 스케줄링 시각화 튜터**

## 1. 프로젝트 요약

xv6 Tutor는 학생들이 xv6 스타일의 프로세스 상태 변화와 스케줄링 흐름을 시각적으로 이해할 수 있도록 돕는 교육용 **LLM for OS** 프로젝트입니다.

이 프로젝트는 실제 운영체제에 들어갈 production-level scheduler를 만드는 것이 아니라, 운영체제 내부에서 보이지 않는 스케줄링 동작을 시각화하고 설명 가능하게 만드는 것을 목표로 합니다. 시스템은 프로세스 상태, ready queue, CPU 할당, preemption, 종료 과정, 스케줄링 지표를 시각화합니다. LLM은 스케줄링 trace를 설명하고, 성능 문제를 진단하며, what-if 스케줄링 실험을 제안하는 튜터 역할을 합니다.

LLM은 운영체제를 직접 제어하는 주체가 아닙니다. LLM은 조언 도구로 사용되며, 실제 스케줄링 결정은 우리가 구현한 deterministic scheduler와 evaluator가 수행합니다.

---

## 2. 개발 동기

학생들은 보통 xv6의 스케줄링을 source code, terminal output, 간단한 log를 통해 학습합니다. 하지만 스케줄링은 본질적으로 동적이기 때문에 텍스트만으로 이해하기 어렵습니다.

예를 들어:

- 프로세스는 `RUNNABLE`, `RUNNING`, `SLEEPING`, `TERMINATED` 같은 상태를 오갑니다.
- ready queue는 시간에 따라 계속 변합니다.
- timer interrupt는 preemption을 발생시킬 수 있습니다.
- 스케줄링 정책에 따라 waiting time, response time, turnaround time이 달라집니다.
- convoy effect, starvation, 불공정한 CPU 할당 같은 문제는 직접 관찰하기 어렵습니다.

이 프로젝트는 학생들이 xv6 스타일의 스케줄링 동작을 관찰하고, 이해하고, 실험할 수 있도록 돕는 것을 목표로 합니다.

---

## 3. 프로젝트 방향

이 프로젝트는 다음 방향을 따릅니다.

> **Direction B — LLM for OS**

LLM은 운영체제 학습 도구 안에 통합됩니다. LLM은 scheduling trace와 performance metrics를 입력받고, 이에 대한 설명과 정책 제안을 제공합니다.

실제 OS 스타일의 스케줄링 로직은 우리가 구현한 simulator와 evaluator가 담당합니다.

---

## 4. 핵심 아이디어

시스템은 다음 흐름으로 동작합니다.

```text
xv6-style Workload
        ↓
Scheduler Simulator
        ↓
Event Trace Generator
        ↓
Visual Scheduler Timeline
        ↓
Metrics Collector
        ↓
LLM Tutor / Advisor
        ↓
What-if Scheduling Experiment
        ↓
Evaluator
```

LLM은 왜 특정 프로세스가 기다렸는지, 왜 response time이 증가했는지, 왜 starvation이 발생했는지, 또는 왜 다른 스케줄링 정책이 더 나을 수 있는지를 설명합니다.

단, LLM의 제안은 미리 정의한 평가 조건을 만족할 때만 수용됩니다.

---

## 5. 주요 기능

### 5.1 xv6 스타일 스케줄링 시뮬레이터

시뮬레이터는 xv6 스타일의 기본 프로세스와 스케줄링 동작을 모델링합니다.

각 프로세스는 다음 정보를 가집니다.

```text
pid
arrival_time
burst_time
remaining_time
priority
state
waiting_time
response_time
turnaround_time
```

지원 예정 스케줄링 알고리즘:

- FCFS
- Round Robin
- Priority Scheduling
- MLFQ

---

### 5.2 Event Trace Generator

시뮬레이터는 구조화된 event trace를 생성합니다.

예시:

```json
[
  {
    "time": 0,
    "event": "ARRIVE",
    "pid": 1,
    "state": "RUNNABLE"
  },
  {
    "time": 1,
    "event": "DISPATCH",
    "pid": 1,
    "state": "RUNNING"
  },
  {
    "time": 5,
    "event": "PREEMPT",
    "pid": 1,
    "state": "RUNNABLE"
  },
  {
    "time": 10,
    "event": "EXIT",
    "pid": 1,
    "state": "TERMINATED"
  }
]
```

이 trace는 시각화와 LLM 기반 설명에 모두 사용됩니다.

---

### 5.3 Visual Scheduler Timeline

GUI는 스케줄링 과정을 시각화합니다.

예정된 시각화 요소:

- Process table
- Ready queue
- CPU execution box
- Sleeping/waiting process list
- Gantt chart
- Scheduling metrics panel

목표는 학생들이 scheduler decision이 시간에 따라 process behavior에 어떤 영향을 주는지 이해하도록 돕는 것입니다.

---

### 5.4 LLM Tutor

LLM은 trace와 metrics를 바탕으로 스케줄링 동작을 설명합니다.

LLM이 답할 수 있는 질문 예시:

- 왜 P2 프로세스가 오래 기다렸는가?
- 왜 FCFS에서 waiting time이 커졌는가?
- 왜 Round Robin은 response time을 개선할 수 있는가?
- 이 trace에서 convoy effect는 무엇인가?
- 왜 priority scheduling은 starvation을 유발할 수 있는가?
- aging은 starvation을 어떻게 완화하는가?

---

### 5.5 What-if Scheduling Advisor

LLM은 스케줄링 실험을 제안할 수 있습니다.

예시:

```json
{
  "diagnosis": "Short interactive processes are delayed by a long CPU-bound process.",
  "suggestion": {
    "algorithm": "Round Robin",
    "time_quantum": 4
  },
  "expected_effect": "Response time may improve because CPU time is distributed more frequently."
}
```

그 후 시스템은 제안된 정책을 실행하고 baseline 결과와 비교합니다.

---

### 5.6 Metric-based Evaluator

LLM의 제안은 무조건 수용되지 않습니다.

제안된 정책은 다음 조건을 만족할 때만 수용됩니다.

- 평균 response time이 개선될 것
- 평균 waiting time이 크게 악화되지 않을 것
- starvation이 발생하지 않을 것
- 모든 프로세스가 최종적으로 종료될 것
- scheduling parameter가 유효한 범위 안에 있을 것

예시 결과:

```json
{
  "baseline": "FCFS",
  "suggested_policy": "Round Robin, quantum = 4",
  "accepted": true,
  "reason": {
    "avg_response_time": "12.0 -> 4.2",
    "avg_waiting_time": "18.3 -> 13.1",
    "starvation": false
  }
}
```

---

## 6. 사용되는 OS 개념

이 프로젝트는 다음 운영체제 개념을 직접 사용합니다.

### Process

시스템은 각 프로세스를 PID, state, burst time, priority, scheduling metrics와 함께 모델링합니다.

### Process State

시뮬레이터는 다음과 같은 상태 전이를 시각화합니다.

```text
NEW → RUNNABLE → RUNNING → SLEEPING → RUNNABLE → TERMINATED
```

### CPU Scheduling

프로젝트는 여러 스케줄링 알고리즘을 비교합니다.

- FCFS
- Round Robin
- Priority Scheduling
- MLFQ

### Ready Queue

ready queue를 시각화하여 CPU 할당을 기다리는 프로세스들을 보여줍니다.

### Preemption

Round Robin과 MLFQ를 통해 preemptive scheduling behavior를 보여줍니다.

### Starvation and Aging

Priority scheduling과 MLFQ 시나리오를 통해 starvation과 aging 기반 완화 방법을 보여줄 수 있습니다.

### Scheduling Metrics

시스템은 다음 지표를 계산합니다.

- Waiting time
- Turnaround time
- Response time
- Throughput
- Starvation occurrence

---

## 7. LLM의 역할

LLM은 다음 역할로 사용됩니다.

```text
Tutor
Trace Explainer
Misconception Corrector
Scheduling Advisor
What-if Experiment Recommender
```

LLM은 다음 역할로 사용되지 않습니다.

```text
Kernel Controller
Direct Scheduler
Context-switch Decision Maker
Unverified Policy Executor
```

이 설계는 OS 로직을 deterministic하게 유지하면서, LLM을 설명, 분석, 학습 지원에 활용합니다.

---

## 8. 기술 스택

예정 기술 스택:

```text
Language: Python
LLM Backend: Upstage Solar Pro 3 API
Visualization: Streamlit or React
Scheduler Core: Custom Python simulator
Data Format: JSON event traces
Version Control: GitHub
```

선택적 추가 요소:

```text
xv6 trace integration
Graph visualization
Gantt chart rendering
Scenario presets
```

---

## 9. 데모 시나리오

### Scenario 1: FCFS Convoy Effect

긴 CPU-bound process가 여러 짧은 interactive process보다 먼저 도착하는 상황입니다.

학습 포인트:

```text
FCFS에서는 긴 작업 뒤에 짧은 작업들이 기다리게 되어 average waiting time이 증가할 수 있습니다.
```

---

### Scenario 2: Round Robin Quantum Trade-off

같은 workload를 서로 다른 time quantum으로 실험합니다.

학습 포인트:

```text
큰 quantum은 FCFS처럼 동작할 수 있고, 너무 작은 quantum은 context-switch overhead를 증가시킬 수 있습니다.
```

---

### Scenario 3: Priority Scheduling and Starvation

높은 priority process들이 CPU를 계속 차지하여 낮은 priority process가 오래 기다리는 상황입니다.

학습 포인트:

```text
Priority scheduling은 starvation을 유발할 수 있으며, aging은 이를 완화할 수 있습니다.
```

---

### Scenario 4: LLM-assisted Policy Suggestion

LLM이 trace를 분석하고 새로운 스케줄링 정책을 제안합니다.

학습 포인트:

```text
스케줄링 정책은 무조건 받아들이는 것이 아니라 metrics를 통해 평가되어야 합니다.
```

---

## 10. 평가 계획

이 프로젝트는 scheduling correctness와 educational usefulness를 함께 평가합니다.

### Scheduling Metrics

- Average waiting time
- Average turnaround time
- Average response time
- Throughput
- Starvation occurrence

### LLM Advisor Evaluation

- 설명이 실제 trace와 일치하는지
- 제안된 정책이 유효한지
- 제안된 정책이 metrics를 개선하는지
- 시스템이 제안을 올바르게 수용하거나 거절하는지

### Visualization Evaluation

- GUI가 event trace와 일치하는지
- process state transition이 올바르게 표시되는지
- Gantt chart가 scheduler output과 일치하는지

---

## 11. 프로젝트 마일스톤

### Week 10

- 프로젝트 주제 정의
- 문제 정의 작성
- 시스템 아키텍처 설계
- OS 개념과 핵심 기능 정의

### Week 11

- 기본 scheduler simulator 구현
- FCFS와 Round Robin 구현
- event trace 생성
- 기본 scheduling metrics 계산

### Week 12

- Priority Scheduling과 MLFQ 추가
- 초기 visualizer 구현
- Solar API 연결
- LLM trace explanation 구현

### Week 13

- what-if policy advisor 추가
- evaluator 구현
- 데모 시나리오 준비
- 평가 실험 진행
- 기술 보고서와 발표 자료 초안 작성

### Week 14

- 애플리케이션 완성
- 보고서 완성
- 영어 발표 슬라이드 완성
- 최종 데모

---

## 12. 실행 방법

> 구현이 진행되면서 업데이트할 예정입니다.

예시:

```bash
git clone <repository-url>
cd <repository-name>
pip install -r requirements.txt
streamlit run app.py
```

환경 변수:

```bash
UPSTAGE_API_KEY=your_api_key_here
```

API key는 GitHub에 커밋하지 않습니다.

---

## 13. Repository Structure

예정 구조:

```text
.
├── README.md
├── README_ko.md
├── requirements.txt
├── app.py
├── src/
│   ├── scheduler/
│   │   ├── fcfs.py
│   │   ├── round_robin.py
│   │   ├── priority.py
│   │   └── mlfq.py
│   ├── trace/
│   │   └── event_logger.py
│   ├── llm/
│   │   └── advisor.py
│   ├── evaluator/
│   │   └── metrics.py
│   └── visualization/
│       └── dashboard.py
├── scenarios/
│   ├── convoy_effect.json
│   ├── rr_quantum_tradeoff.json
│   └── priority_starvation.json
├── docs/
│   ├── architecture.md
│   ├── development_process.md
│   └── report.md
└── assets/
    └── demo/
```

---

## 14. 팀 역할

> 추후 업데이트 예정입니다.

| Role | Responsibility | Member |
|---|---|---|
| Project Lead / Architecture | 전체 설계, GitHub 관리, 보고서 구조 | TBD |
| Scheduler Core | 스케줄링 시뮬레이터, metrics, evaluator | TBD |
| LLM Integration | Solar API, prompt design, advisor output format | TBD |
| Visualization / Documentation | GUI, demo scenarios, README, slides | TBD |

---

## 15. 현재 상태

- 프로젝트 방향 선택: **LLM for OS**
- 메인 주제: **Educational xv6-style scheduling tutor**
- 초기 README 작성
- scheduler simulator와 event trace generation부터 구현 시작 예정