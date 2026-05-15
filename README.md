# Visual Scheduler

**An LLM-Assisted xv6 Scheduling Algorithm Lab**

## 1. Project Summary
Visual Scheduler is an educational LLM-for-OS project that extends xv6 with multiple Scheduling Algorithms and visualizes how each algorithm affects process execution.

The system allows an LLM to analyze workload characteristics and recommend a suitable Scheduling Algorithm. 
However, the LLM does not directly control the scheduler. Actual scheduling is performed inside xv6, and the recommendation is evaluated using Scheduling Metrics such as waiting time, response time, turnaround time, throughput, and starvation occurrence.

## 2. Motivation

Scheduling is one of the most important concepts in operating systems, but it is difficult to understand only by reading source code or terminal output.

In xv6, the default scheduler is simple enough for students to study, but the actual behavior of scheduling is still dynamic and hard to observe directly. 
Processes move between states, wait in the ready queue, receive CPU time, get preempted, and eventually terminate. Different Scheduling Algorithms can produce very different results even with the same workload.

For example, FCFS can suffer from the convoy effect, Priority Scheduling can cause starvation, and Round Robin can improve response time depending on the time quantum. These behaviors are easier to understand when students can visually observe the scheduling trace and compare Scheduling Metrics.

Visual Scheduler aims to help students learn OS scheduling by combining:

- xv6-based Scheduling Algorithm implementation
- LLM-based Scheduling Algorithm recommendation
- Scheduling Trace visualization
- Metrics-based comparison between algorithms

The goal is not to build a production-level scheduler, but to build an educational Scheduling Algorithm Lab where students can experiment with different algorithms and understand why each algorithm behaves differently.

## 3. Project Direction: LLM for OS

This project follows **Direction B: LLM for OS**.

The LLM is integrated into an operating-system scheduling experiment environment. It analyzes workload characteristics and recommends a suitable Scheduling Algorithm. However, the LLM does not directly execute scheduling decisions. The actual scheduling is performed inside xv6.

This project is not a simple LLM chatbot or a Python-only scheduling calculator. The core OS component is the xv6 scheduler, which is extended with multiple Scheduling Algorithms. The LLM acts as an advisor that provides scheduling hints, and the system verifies the recommendation using actual Scheduling Metrics.

In this design:

- xv6 performs the actual scheduling.
- The LLM recommends a Scheduling Algorithm based on workload characteristics.
- Scheduling Traces are collected from xv6.
- The GUI visualizes process execution and Scheduling Metrics.
- The evaluator checks whether the LLM recommendation was actually useful.

The LLM recommendation is treated as a hypothesis, not as the final answer.

## 4. Core Architecture

User-defined Workload
        ↓
LLM Scheduling Advisor
        ↓
Scheduling Algorithm Recommendation
        ↓
xv6 Scheduler
  RR / FCFS / Priority / MLFQ / SJF-SRTF Prediction
        ↓
Scheduling Trace Collector
        ↓
Metrics Evaluator
        ↓
Visual Comparison GUI

## 5. Main Pipeline

1. **Workload Definition**
   - The user defines processes with arrival time, burst time, priority, and workload type.

2. **LLM Scheduling Algorithm Recommendation**
   - The LLM analyzes the workload and recommends a suitable Scheduling Algorithm.

3. **xv6 Scheduling Execution**
   - xv6 executes the workload using the selected Scheduling Algorithm.

4. **Scheduling Trace Collection**
   - The system collects scheduling events such as dispatch, preemption, waiting, wakeup, and termination.

5. **Visualization**
   - The GUI visualizes the ready queue, running process, process state transitions, and Gantt chart.

6. **Metrics-based Evaluation**
   - The system compares Scheduling Algorithms using waiting time, response time, turnaround time, throughput, and starvation occurrence.

## 6. Main Features

### 6.1 Multiple Scheduling Algorithms in xv6

Visual Scheduler extends xv6 with multiple Scheduling Algorithms.

Planned algorithms include:

- Round Robin
- FCFS
- Priority Scheduling
- MLFQ
- Optional: SJF / SRTF with burst prediction

The default xv6 Round Robin scheduler is preserved as the baseline. Additional Scheduling Algorithms are implemented so that students can compare how each algorithm behaves under the same workload.

---

### 6.2 Scheduling Algorithm Control Interface

The system provides a way to choose which Scheduling Algorithm xv6 should use.

Planned control features:

- `setscheduler`
- `getscheduler`
- `setpriority`
- `getpriority`

These interfaces allow users to run the same workload under different Scheduling Algorithms and compare the results.

## 7. Scheduling Algorithms

Visual Scheduler plans to support the following Scheduling Algorithms.

### Round Robin

Round Robin is the default baseline Scheduling Algorithm in xv6. It gives runnable processes CPU time in turn and prevents a single process from monopolizing the CPU.

### FCFS

FCFS executes processes in arrival order. It is simple, but it can suffer from the convoy effect when a long CPU-bound process blocks shorter processes.

### Priority Scheduling

Priority Scheduling selects processes based on priority values. It can improve the response of important processes, but low-priority processes may suffer from starvation.

### MLFQ

MLFQ uses multiple queues with different priorities and time quantums. It can favor interactive processes while demoting long CPU-bound processes. Aging can be used to reduce starvation.

### SJF / SRTF with Burst Prediction

SJF and SRTF are theoretically powerful because they prioritize the process with the shortest next CPU burst. 
However, the next CPU burst cannot be known exactly in a real OS. In this project, SJF/SRTF may be implemented as an optional educational Scheduling Algorithm using burst prediction. 
The LLM may be used as a burst-prediction hint oracle, and its predictions can be compared with traditional exponential averaging.

## 8. LLM Role

The LLM is used as a **Scheduling Advisor**, not as the scheduler itself.

The LLM can:

- Analyze workload characteristics
- Recommend a suitable Scheduling Algorithm
- Explain why the algorithm may fit the workload
- Predict CPU burst hints for SJF/SRTF experiments
- Explain Scheduling Traces and Scheduling Metrics

The LLM cannot:

- Directly choose the next process at every timer tick
- Modify xv6 kernel state directly
- Perform context switches
- Replace the xv6 scheduler
- Apply unverified recommendations automatically

The LLM recommendation is treated as a hypothesis. The system verifies it by running the workload inside xv6 and comparing the resulting Scheduling Metrics.

## 9. OS Concepts Used

This project directly uses the following operating-system concepts:

- **Process**
  - Each process has a PID, state, arrival time, burst time, priority, and runtime information.

- **Process State**
  - Processes move through states such as READY, RUNNING, WAITING, and TERMINATED.

- **CPU Scheduling**
  - The project implements and compares multiple Scheduling Algorithms inside xv6.

- **Ready Queue**
  - The system tracks which processes are waiting for CPU allocation.

- **Preemption**
  - Round Robin, MLFQ, and SRTF demonstrate preemptive scheduling behavior.

- **System Calls**
  - Additional system calls may be added to control the selected Scheduling Algorithm or process priority.

- **Starvation and Aging**
  - Priority Scheduling and MLFQ can demonstrate starvation, and aging can be used as a mitigation technique.

- **Scheduling Metrics**
  - The system calculates waiting time, response time, turnaround time, throughput, and starvation occurrence.

## 10. Evaluation Plan

Visual Scheduler is evaluated from three perspectives:

1. Scheduling correctness
2. LLM recommendation quality
3. Educational usefulness

---

### 10.1 Scheduling Correctness

We evaluate whether each Scheduling Algorithm is implemented correctly.

Evaluation items:

- Correct process selection
- Correct preemption behavior
- Correct priority handling
- Correct queue behavior for MLFQ
- Correct process state transitions
- Correct Scheduling Trace generation

For each test workload, we check whether the actual execution order matches the expected behavior of the selected Scheduling Algorithm.

---

### 10.2 Scheduling Metrics

The system compares Scheduling Algorithms using the following metrics:

- Average waiting time
- Average response time
- Average turnaround time
- Throughput
- Starvation occurrence

Definitions:

```text
response time = first_run_time - arrival_time
turnaround time = finish_time - arrival_time
waiting time = turnaround_time - total_cpu_burst_time
throughput = completed_process_count / total_execution_time
```

## 11. Tech Stack

### Operating System Environment

- xv6-riscv
- QEMU
- RISC-V toolchain
- WSL or Linux environment

### Kernel / OS Implementation

- C
- xv6 kernel source code
- xv6 system calls
- xv6 user programs

### Host-side Tooling

- Python
- Trace parser
- Metrics evaluator
- JSON-based data format

### Visualization

Planned options:

- Streamlit
- Plotly or matplotlib for Gantt chart
- pandas for table-based metrics display

Streamlit is preferred for the first prototype because it allows fast GUI development.

### LLM Backend

- Upstage Solar Pro 3 API

The LLM is used for Scheduling Algorithm recommendation and explanation. API keys must not be committed to GitHub.

### Version Control

- Git
- GitHub