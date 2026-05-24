# LLM Sched Copilot

**The LLM-Assisted Scheduler for xv6**

LLM Sched Copilot is an **LLM-for-OS** project that uses an LLM as a high-level decision support layer for xv6 CPU scheduling.

The LLM analyzes workload summaries and Scheduling Trace Logs, recommends a suitable **Scheduling Algorithm**, suggests algorithm parameters, proposes runtime corrections when scheduling problems are detected, and explains the execution result in natural language.

The LLM does **not** replace the xv6 scheduler.  
xv6 remains the execution authority.  
The Metrics Evaluator verifies the LLM's judgment using concrete scheduling metrics.  
The GUI visualizes the whole process as an observability dashboard.

> **LLM suggests. Algorithm Guard checks. xv6 executes. Metrics verify. GUI explains.**

---

## 1. Project Direction

This project follows **Direction B: LLM for OS**.

The project integrates an LLM into a classical OS problem: **CPU Scheduling**.

Instead of using the LLM as a simple chatbot, this project uses the LLM as a scheduling decision support layer:

- The LLM interprets workload characteristics.
- The LLM recommends a Scheduling Algorithm and parameters.
- The LLM proposes runtime corrections when trace monitoring detects problems.
- The LLM explains Scheduling Trace Logs and Scheduling Metrics.
- The LLM generates feedback rules for future recommendations.

The actual Scheduling Algorithm execution is performed by xv6.

---

## 2. Core Idea

Traditional xv6 scheduling behavior is usually visible only through terminal logs or source code.  
This project turns that low-level behavior into a trace-verified scheduling workflow.

```text
User Workload / Goal
        ↓
Workload Analyzer
        ↓
LLM Workload Interpreter
        ↓
LLM Scheduling Algorithm Advisor
        ↓
Algorithm Guard
        ↓
xv6 Scheduling Algorithm Execution
        ↓
Scheduling Trace Collector
        ↓
Metrics Evaluator
        ↓
Runtime Correction / Trace Explanation / Feedback Rule
        ↓
GUI Observability Dashboard
```

The main question of this project is:

> Can an LLM help choose, tune, correct, and explain xv6 Scheduling Algorithms using workload summaries and Scheduling Trace Logs?

---

## 3. System Principle

The system separates responsibility clearly.

| Component | Responsibility |
|---|---|
| LLM | Interprets workload, recommends Scheduling Algorithm, proposes correction, explains result |
| Algorithm Guard | Checks whether the LLM output is valid and safe to apply |
| xv6 | Executes the selected Scheduling Algorithm |
| Trace Monitor | Collects Scheduling Trace Logs and detects runtime events |
| Metrics Evaluator | Verifies the scheduling result with numerical metrics |
| GUI | Visualizes recommendation, execution, correction, metrics, and explanation |

The LLM is a **decision support layer**, not the kernel scheduler.

The LLM cannot:

- choose the next process at every timer tick
- directly modify kernel state
- directly perform context switches
- apply unverified recommendations automatically
- replace xv6 Scheduling Algorithms

---

## 4. Supported Scheduling Algorithms

The project targets the following Scheduling Algorithms.

### 4.1 Round Robin

Round Robin is the baseline Scheduling Algorithm.  
It gives runnable processes CPU time in turn and prevents a single process from monopolizing the CPU.

### 4.2 FCFS

FCFS executes processes in arrival order.  
It is simple, but it can suffer from the convoy effect when a long CPU-bound process arrives before short jobs.

### 4.3 Priority Scheduling + Aging

Priority Scheduling selects a process based on priority.  
It can improve the response of important processes, but low-priority processes may suffer from starvation.

Aging is used to reduce starvation by gradually increasing the effective priority of waiting processes.

### 4.4 MLFQ

MLFQ uses multiple queues with different time quantums.  
It can favor short or interactive jobs while demoting long CPU-bound jobs.

LLM Sched Copilot can suggest MLFQ parameters such as:

- number of queues
- time quantum for each queue
- aging threshold
- boost interval

### 4.5 SJF / SRTF + Burst Prediction

SJF and SRTF are powerful Scheduling Algorithms because they favor short CPU bursts.

However, a real OS cannot know the exact next CPU burst in advance.  
Therefore, this project treats burst prediction as an experimental feature.

Possible predictors:

- traditional exponential averaging
- LLM-assisted burst prediction
- LLM-assisted predictor parameter tuning

The LLM must not receive the actual future CPU burst as input.

---

## 5. LLM Roles

The LLM works in three phases.

---

### 5.1 Before Running

#### 5.1.1 Workload Interpreter

The LLM receives a workload summary generated from observable workload information.

It may infer:

- workload type
- CPU-bound tendency
- interactive tendency
- burst variance
- priority distribution
- starvation risk
- target metric

Example output:

```json
{
  "workload_type": "interactive_heavy",
  "target_metric": "avg_response_time",
  "main_risks": ["poor_response_time", "starvation"],
  "reason": "The workload contains multiple short interactive jobs mixed with long CPU-bound jobs."
}
```

The LLM does not know exact future execution results.

#### 5.1.2 Scheduling Algorithm Advisor

The LLM recommends a Scheduling Algorithm and parameters.

Example output:

```json
{
  "recommended_scheduling_algorithm": "MLFQ",
  "params": {
    "queues": 3,
    "quantum": [2, 4, 8],
    "aging_threshold": 30,
    "boost_interval": 100
  },
  "target_metric": "avg_response_time",
  "risk": ["starvation if aging is too weak"],
  "reason": "MLFQ can favor short interactive jobs while still allowing long CPU-bound jobs to make progress."
}
```

The recommendation is sent to the Algorithm Guard before execution.

---

### 5.2 Running

#### 5.2.1 Runtime Correction Proposer

During execution, the Trace Monitor watches the Scheduling Trace Log.

If a scheduling problem is detected, the system summarizes the event and asks the LLM for a correction.

Example detected events:

- starvation warning
- poor response time
- too many preemptions
- long CPU-bound domination
- high waiting time
- burst prediction failure

Example correction output:

```json
{
  "correction_type": "parameter_update",
  "current_scheduling_algorithm": "MLFQ",
  "new_params": {
    "quantum": [2, 4, 8],
    "aging_threshold": 20,
    "boost_interval": 80
  },
  "reason": "The previous aging threshold was too high, so low-priority processes waited too long."
}
```

Possible correction types:

- parameter update
- Scheduling Algorithm change
- process hint update
- aging threshold adjustment
- time quantum adjustment

The correction is also checked by the Algorithm Guard.

The correction is applied from the next scheduling point, not by interrupting every timer tick with an LLM call.

---

### 5.3 After Running

#### 5.3.1 Trace Explainer

After execution, the system summarizes:

- Scheduling Trace Log
- Scheduling Metrics
- detected runtime events
- comparison with other Scheduling Algorithms

Then the LLM explains the result in natural language.

Example output:

```json
{
  "summary": "FCFS performed poorly on this workload.",
  "detected_pattern": "convoy_effect",
  "main_reason": "A long CPU-bound process arrived first and delayed short interactive jobs.",
  "evidence": [
    "P1 ran from tick 0 to tick 40.",
    "P2 arrived at tick 5 but first ran at tick 41.",
    "Average response time was much higher than MLFQ."
  ],
  "suggestion": "MLFQ or Round Robin would reduce response time for short jobs."
}
```

The Trace Explainer helps users understand not only what happened, but why it happened.

#### 5.3.2 Feedback Rule Generator

If the LLM recommendation was poor, the system asks the LLM to generate a feedback rule.

Example:

```json
{
  "failed_case": {
    "llm_selected": "FCFS",
    "actual_best": "MLFQ",
    "regret_score": 0.42
  },
  "feedback_rule": "If burst variance is high and many interactive jobs arrive after a long CPU-bound job, avoid FCFS and prefer MLFQ or Round Robin."
}
```

The feedback rule can be used in later LLM prompts.

---

## 6. Algorithm Guard

The Algorithm Guard prevents invalid or unsafe LLM output from being applied.

It checks:

- whether the recommended Scheduling Algorithm is implemented
- whether the parameters are in valid ranges
- whether required information exists
- whether burst prediction is available when SJF/SRTF is requested
- whether the correction type is supported
- whether the output follows the required JSON schema

Example decisions:

```json
{
  "guard_result": "accepted",
  "reason": "MLFQ is implemented and all parameters are valid."
}
```

```json
{
  "guard_result": "rejected",
  "reason": "SRTF requires burst prediction, but no predictor output was provided.",
  "fallback_scheduling_algorithm": "MLFQ"
}
```

---

## 7. Scheduling Trace Log

The Scheduling Trace Log records important scheduling events.

Example:

```text
[SCHED] tick=12 algo=RR event=DISPATCH pid=3 state=RUNNING queue=0
[SCHED] tick=16 algo=RR event=PREEMPT pid=3 state=RUNNABLE queue=0
[SCHED] tick=17 algo=RR event=DISPATCH pid=4 state=RUNNING queue=0
[SCHED] tick=45 algo=RR event=EXIT pid=4 state=ZOMBIE queue=0
```

Target events:

- ARRIVE
- DISPATCH
- PREEMPT
- SLEEP
- WAKEUP
- EXIT
- QUEUE_CHANGE
- CORRECTION_APPLIED

---

## 8. Metrics Evaluator

The Metrics Evaluator verifies whether the LLM recommendation was actually useful.

Metrics:

- average waiting time
- average response time
- average turnaround time
- throughput
- max waiting time
- starvation occurrence
- preemption count
- burst prediction error
- regret score

Definitions:

```text
response time = first_run_time - arrival_time
turnaround time = finish_time - arrival_time
waiting time = turnaround_time - total_cpu_burst_time
throughput = completed_process_count / total_execution_time
```

Recommendation judgment:

```text
SUCCESS      = LLM selected the best or near-best Scheduling Algorithm
NEAR-SUCCESS = LLM result is close to the best result
FAIL         = LLM result is clearly worse than the best result
```

---

## 9. GUI Observability Dashboard

The GUI is not the core scheduler.  
It is the observability dashboard that visualizes the whole LLM-assisted scheduling process.

The GUI shows:

- workload summary
- LLM Scheduling Algorithm recommendation
- Algorithm Guard result
- live or replayed Scheduling Trace Log
- Gantt chart
- ready queue timeline
- process state table
- runtime correction event
- before/after metrics
- Trace Explainer result
- Feedback Rule Generator result

Main dashboard message:

> **LLM suggests. xv6 executes. Metrics verify. GUI explains.**

---

## 10. Example Demo Scenario

### Scenario: Starvation under Priority Scheduling

1. User goal:
   - interactive jobs should respond quickly
   - no process should starve

2. LLM recommendation:
   - Priority Scheduling + weak aging

3. xv6 execution:
   - low-priority process waits too long

4. Trace Monitor:
   - starvation warning detected

5. LLM correction:
   - reduce aging threshold
   - or change Scheduling Algorithm to MLFQ

6. Algorithm Guard:
   - validates the correction

7. xv6:
   - applies correction from the next scheduling point

8. Metrics Evaluator:
   - max waiting time decreases
   - starvation disappears

9. GUI:
   - shows before/after Gantt chart
   - shows metrics improvement
   - shows natural-language trace explanation

---

## 11. Data Files

Planned data files:

```text
workloads/*.json
outputs/workload_summary.json
outputs/recommendation.json
outputs/guard_decision.json
outputs/trace.jsonl
outputs/metrics.json
outputs/runtime_events.json
outputs/correction.json
outputs/trace_explanation.json
outputs/feedback_rules.md
```

---

## 12. Planned Repository Structure

```text
.
├── README.md
├── docs/
│   ├── architecture.md
│   ├── trace_format.md
│   ├── data_format.md
│   └── evaluation_plan.md
├── workloads/
│   ├── convoy_effect.json
│   ├── interactive_heavy.json
│   ├── priority_starvation.json
│   └── mixed_workload.json
├── tools/
│   ├── workload_analyzer.py
│   ├── llm_advisor.py
│   ├── algorithm_guard.py
│   ├── trace_parser.py
│   ├── metrics.py
│   ├── event_detector.py
│   ├── runtime_correction.py
│   ├── trace_explainer.py
│   └── feedback_generator.py
├── dashboard/
│   └── dashboard.py          # Streamlit legacy dashboard
├── dashboard_test/           # Static fixture UI dashboard (design/inspection)
│   ├── src/data/demoData.js
│   └── README.md
├── dashboard_live/           # Final live data dashboard
│   ├── src/                  # React app with props-driven components
│   ├── public/live-data/     # Generated by run_live_dashboard_pipeline.py
│   └── README.md
├── scripts/
│   └── run_live_dashboard_pipeline.py
└── xv6-riscv/
```

## Dashboard modes

| Dashboard        | Purpose                           | Command                          |
|------------------|-----------------------------------|----------------------------------|
| `dashboard_test` | Static fixture UI (design/inspect)| `cd dashboard_test && npm run dev` |
| `dashboard_live` | Final project dashboard (live data)| `cd dashboard_live && npm run dev` |
| `dashboard/`     | Streamlit legacy dashboard        | `streamlit run dashboard/dashboard.py` |

### Run dashboard_test

```bash
cd dashboard_test
npm install
npm run dev     # http://localhost:5173
```

### Run dashboard_live

```bash
# Step 1: generate live data
python3 scripts/run_live_dashboard_pipeline.py

# Step 2: start dashboard
cd dashboard_live
npm install
npm run dev     # http://localhost:5174
```

### Build

```bash
cd dashboard_test && npm run build
cd dashboard_live && npm run build
```

See `docs/demo_runbook.md` for full pipeline details.

---

## 13. OS Concepts Used

This project directly uses the following OS concepts:

- process
- process state
- CPU scheduling
- ready queue
- preemption
- context switch
- system calls
- priority
- starvation
- aging
- Scheduling Metrics
- trace-based observability

---

## 14. Tech Stack

### OS Environment

- xv6-riscv
- QEMU
- RISC-V toolchain
- WSL or Linux

### xv6 Implementation

- C
- xv6 scheduler
- xv6 system calls
- xv6 user programs

### Host-side Tools

- Python
- JSON / JSONL
- trace parser
- Metrics Evaluator
- LLM API client

### GUI

- Streamlit
- pandas
- Plotly or matplotlib

### LLM Backend

- Upstage Solar Pro 3 API

API keys must not be committed to GitHub.

---

## 15. Development Roadmap

### Phase 1 — Basic Trace and Metrics

- implement Scheduling Trace Log
- parse trace into structured data
- calculate basic Scheduling Metrics
- visualize Gantt chart

### Phase 2 — Multiple Scheduling Algorithms

- preserve Round Robin baseline
- implement FCFS
- implement Priority Scheduling + Aging
- implement MLFQ
- add Scheduling Algorithm control interface

### Phase 3 — LLM Scheduling Algorithm Advisor

- generate workload summary
- call Solar Pro 3 API
- receive Scheduling Algorithm recommendation JSON
- validate recommendation with Algorithm Guard

### Phase 4 — Runtime Correction

- detect starvation and poor response time
- request LLM correction
- validate correction
- apply correction from the next scheduling point
- compare before/after metrics

### Phase 5 — Trace Explainer and Feedback Rule Generator

- summarize trace and metrics
- generate natural-language explanation
- generate feedback rules from failed recommendations
- display explanation in GUI

### Phase 6 — Optional Burst Prediction Experiment

- implement traditional exponential averaging
- test LLM-assisted burst prediction
- compare predicted burst and actual burst
- compare SJF/SRTF performance with different predictors

---

## 16. Limitations

- The LLM is not called at every timer tick.
- The LLM does not directly choose the next process.
- The LLM does not directly modify xv6 kernel state.
- Runtime correction is applied only after validation.
- Runtime correction takes effect from the next scheduling point.
- Future CPU bursts are not given to the LLM as answers.
- Controlled workloads may be used for reproducible experiments.

---

## 17. One-sentence Summary

**LLM Sched Copilot is an LLM-for-OS system where an LLM recommends, corrects, and explains xv6 Scheduling Algorithms, while xv6 executes them and metrics verify the result.**
