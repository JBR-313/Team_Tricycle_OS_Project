// fixtures.js — Static fixture data for LLM Scheduler Dashboard UI tests
// interactive_heavy is imported from demoData.js; all others are defined here.

import {
  traces       as _ihTraces,
  recommendation  as _ihRecommendation,
  guardDecision   as _ihGuardDecision,
  metrics         as _ihMetrics,
  workloadSummary as _ihWorkloadSummary,
  traceExplanation as _ihTraceExplanation,
  ALGOS           as _ihALGOS,
} from './demoData.js';

// ─────────────────────────────────────────────
// 1. interactive_heavy — re-exported from demoData
// ─────────────────────────────────────────────
export const interactive_heavy = {
  label: 'Interactive Heavy',
  description: 'Mixed short interactive + long CPU-bound jobs; MLFQ recommended.',
  traces: _ihTraces,
  recommendation: _ihRecommendation,
  guardDecision: _ihGuardDecision,
  metrics: _ihMetrics,
  workloadSummary: _ihWorkloadSummary,
  traceExplanation: _ihTraceExplanation,
  ALGOS: _ihALGOS,
};

// ─────────────────────────────────────────────
// 2. cpu_bound — 3 CPU-heavy processes, FCFS recommended
// ─────────────────────────────────────────────
export const cpu_bound = {
  label: 'CPU Bound',
  description: '3 CPU-heavy processes; FCFS avoids RR overhead; FCFS recommended.',
  traces: {
    RR: [
      // P1 arrives t=0, burst=12; P2 arrives t=5, burst=10; P3 arrives t=10, burst=8
      { tick: 0,  algo: 'RR', event: 'ARRIVE',   pid: 1, state: 'RUNNABLE', queue: 0, priority: 5 },
      { tick: 0,  algo: 'RR', event: 'DISPATCH',  pid: 1, state: 'RUNNING',  queue: 0 },
      { tick: 4,  algo: 'RR', event: 'PREEMPT',   pid: 1, state: 'RUNNABLE', queue: 0, reason: 'quantum_expired' },
      { tick: 4,  algo: 'RR', event: 'DISPATCH',  pid: 1, state: 'RUNNING',  queue: 0 },
      { tick: 5,  algo: 'RR', event: 'ARRIVE',    pid: 2, state: 'RUNNABLE', queue: 0, priority: 5 },
      { tick: 8,  algo: 'RR', event: 'PREEMPT',   pid: 1, state: 'RUNNABLE', queue: 0, reason: 'quantum_expired' },
      { tick: 8,  algo: 'RR', event: 'DISPATCH',  pid: 2, state: 'RUNNING',  queue: 0 },
      { tick: 10, algo: 'RR', event: 'ARRIVE',    pid: 3, state: 'RUNNABLE', queue: 0, priority: 5 },
      { tick: 12, algo: 'RR', event: 'PREEMPT',   pid: 2, state: 'RUNNABLE', queue: 0, reason: 'quantum_expired' },
      { tick: 12, algo: 'RR', event: 'DISPATCH',  pid: 3, state: 'RUNNING',  queue: 0 },
      { tick: 16, algo: 'RR', event: 'PREEMPT',   pid: 3, state: 'RUNNABLE', queue: 0, reason: 'quantum_expired' },
      { tick: 16, algo: 'RR', event: 'DISPATCH',  pid: 1, state: 'RUNNING',  queue: 0 },
      { tick: 20, algo: 'RR', event: 'PREEMPT',   pid: 1, state: 'RUNNABLE', queue: 0, reason: 'quantum_expired' },
      { tick: 20, algo: 'RR', event: 'DISPATCH',  pid: 2, state: 'RUNNING',  queue: 0 },
      { tick: 24, algo: 'RR', event: 'PREEMPT',   pid: 2, state: 'RUNNABLE', queue: 0, reason: 'quantum_expired' },
      { tick: 24, algo: 'RR', event: 'DISPATCH',  pid: 3, state: 'RUNNING',  queue: 0 },
      { tick: 26, algo: 'RR', event: 'EXIT',       pid: 3, state: 'ZOMBIE',   queue: 0, turnaround: 16, waiting: 8,  response: 2 },
      { tick: 26, algo: 'RR', event: 'DISPATCH',  pid: 1, state: 'RUNNING',  queue: 0 },
      { tick: 28, algo: 'RR', event: 'EXIT',       pid: 1, state: 'ZOMBIE',   queue: 0, turnaround: 28, waiting: 16, response: 0 },
      { tick: 28, algo: 'RR', event: 'DISPATCH',  pid: 2, state: 'RUNNING',  queue: 0 },
      { tick: 30, algo: 'RR', event: 'EXIT',       pid: 2, state: 'ZOMBIE',   queue: 0, turnaround: 25, waiting: 15, response: 3 },
    ],
    FCFS: [
      // P1 runs to completion first, no preemption — good for CPU-bound
      { tick: 0,  algo: 'FCFS', event: 'ARRIVE',   pid: 1, state: 'RUNNABLE', queue: 0, priority: 5 },
      { tick: 0,  algo: 'FCFS', event: 'DISPATCH',  pid: 1, state: 'RUNNING',  queue: 0 },
      { tick: 5,  algo: 'FCFS', event: 'ARRIVE',    pid: 2, state: 'RUNNABLE', queue: 0, priority: 5 },
      { tick: 10, algo: 'FCFS', event: 'ARRIVE',    pid: 3, state: 'RUNNABLE', queue: 0, priority: 5 },
      { tick: 12, algo: 'FCFS', event: 'EXIT',       pid: 1, state: 'ZOMBIE',   queue: 0, turnaround: 12, waiting: 0, response: 0 },
      { tick: 12, algo: 'FCFS', event: 'DISPATCH',  pid: 2, state: 'RUNNING',  queue: 0 },
      { tick: 22, algo: 'FCFS', event: 'EXIT',       pid: 2, state: 'ZOMBIE',   queue: 0, turnaround: 17, waiting: 7, response: 7 },
      { tick: 22, algo: 'FCFS', event: 'DISPATCH',  pid: 3, state: 'RUNNING',  queue: 0 },
      { tick: 30, algo: 'FCFS', event: 'EXIT',       pid: 3, state: 'ZOMBIE',   queue: 0, turnaround: 20, waiting: 12, response: 12 },
    ],
    Priority: [
      // All same priority=5, degenerates to FCFS order
      { tick: 0,  algo: 'Priority', event: 'ARRIVE',   pid: 1, state: 'RUNNABLE', queue: 0, priority: 5 },
      { tick: 0,  algo: 'Priority', event: 'DISPATCH',  pid: 1, state: 'RUNNING',  queue: 0 },
      { tick: 5,  algo: 'Priority', event: 'ARRIVE',    pid: 2, state: 'RUNNABLE', queue: 0, priority: 5 },
      { tick: 10, algo: 'Priority', event: 'ARRIVE',    pid: 3, state: 'RUNNABLE', queue: 0, priority: 5 },
      { tick: 12, algo: 'Priority', event: 'EXIT',       pid: 1, state: 'ZOMBIE',   queue: 0, turnaround: 12, waiting: 0, response: 0 },
      { tick: 12, algo: 'Priority', event: 'DISPATCH',  pid: 2, state: 'RUNNING',  queue: 0 },
      { tick: 22, algo: 'Priority', event: 'EXIT',       pid: 2, state: 'ZOMBIE',   queue: 0, turnaround: 17, waiting: 7, response: 7 },
      { tick: 22, algo: 'Priority', event: 'DISPATCH',  pid: 3, state: 'RUNNING',  queue: 0 },
      { tick: 30, algo: 'Priority', event: 'EXIT',       pid: 3, state: 'ZOMBIE',   queue: 0, turnaround: 20, waiting: 12, response: 12 },
    ],
  },
  recommendation: {
    recommended_scheduling_algorithm: 'FCFS',
    params: { quantum: null },
    target_metric: 'avg_turnaround_time',
    risks: ['convoy_effect_if_mixed_workload'],
    reason: 'All processes are CPU-bound with similar burst lengths. FCFS avoids RR context-switch overhead and convoy effect is minimal when bursts are uniform.',
    workload_interpretation: {
      workload_type: 'cpu_bound',
      main_risks: ['context_switch_overhead'],
    },
    llm_model: 'solar-pro3',
    timestamp: '2026-05-22T11:00:00Z',
  },
  guardDecision: {
    guard_result: 'accepted',
    scheduling_algorithm: 'FCFS',
    params: { quantum: null },
    reason: 'FCFS is implemented and no parameters are required.',
    original_recommendation: 'FCFS',
    fallback_used: false,
  },
  metrics: {
    scheduling_algorithm: 'FCFS',
    params: { quantum: null },
    process_count: 3,
    completed_count: 3,
    total_execution_time: 30,
    avg_response_time: 6.3,
    avg_turnaround_time: 16.3,
    avg_waiting_time: 6.3,
    throughput: 0.1,
    max_waiting_time: 12,
    starvation_occurred: false,
    starvation_pids: [],
    preemption_count: 0,
    per_process: [
      { pid: 1, arrival_time: 0,  first_run_time: 0,  finish_time: 12, response_time: 0,  turnaround_time: 12, waiting_time: 0  },
      { pid: 2, arrival_time: 5,  first_run_time: 12, finish_time: 22, response_time: 7,  turnaround_time: 17, waiting_time: 7  },
      { pid: 3, arrival_time: 10, first_run_time: 22, finish_time: 30, response_time: 12, turnaround_time: 20, waiting_time: 12 },
    ],
    comparison: {
      RR: {
        avg_waiting_time: 13.0,
        avg_response_time: 1.7,
        avg_turnaround_time: 24.3,
        throughput: 0.1,
        max_waiting_time: 16,
        preemption_count: 7,
        starvation_occurred: false,
        burst_prediction_error: null,
        judgment: 'FAIL',
      },
      FCFS: {
        avg_waiting_time: 6.3,
        avg_response_time: 6.3,
        avg_turnaround_time: 16.3,
        throughput: 0.1,
        max_waiting_time: 12,
        preemption_count: 0,
        starvation_occurred: false,
        burst_prediction_error: null,
        judgment: 'SUCCESS',
      },
      Priority: {
        avg_waiting_time: 6.3,
        avg_response_time: 6.3,
        avg_turnaround_time: 16.3,
        throughput: 0.1,
        max_waiting_time: 12,
        preemption_count: 0,
        starvation_occurred: false,
        burst_prediction_error: null,
        judgment: 'NEAR-SUCCESS',
      },
    },
    judgment: 'NEAR-SUCCESS',
    regret_score: 0.04,
    workload_file: 'workloads/cpu_bound.json',
  },
  workloadSummary: {
    process_count: 3,
    avg_arrival_gap: 5.0,
    cpu_bound_ratio: 1.0,
    interactive_ratio: 0.0,
    avg_priority: 5.0,
    priority_variance: 0.0,
    has_starvation_risk: false,
    burst_count_distribution: { min: 1, max: 1, avg: 1.0 },
    total_cpu_work: 30,
    workload_file: 'workloads/cpu_bound.json',
    workload_type: 'cpu_bound',
    target_metric: 'avg_turnaround_time',
    main_risks: ['context_switch_overhead'],
    reason: 'All processes are CPU-bound. FCFS minimises context-switch overhead.',
  },
  traceExplanation: {
    scheduling_algorithm: 'FCFS',
    summary: 'FCFS performed well on this uniformly CPU-bound workload, achieving low turnaround with zero preemptions.',
    detected_pattern: 'cpu_favorable',
    main_reason: 'All processes have similar CPU burst lengths; FCFS avoids the overhead of repeated context switches imposed by RR.',
    evidence: [
      'P1 ran uninterrupted from tick 0 to tick 12.',
      'P2 waited only 7 ticks before receiving the CPU.',
      'Preemption count = 0 vs 7 for RR on the same workload.',
    ],
    suggestion: 'If workload mix changes to include interactive jobs, consider switching to MLFQ.',
    runtime_corrections_applied: 0,
    llm_model: 'solar-pro3',
    timestamp: '2026-05-22T11:05:00Z',
  },
  ALGOS: ['RR', 'FCFS', 'Priority'],
};

// ─────────────────────────────────────────────
// 3. starvation_risk — Priority scheduling, P1 starves
// ─────────────────────────────────────────────
export const starvation_risk = {
  label: 'Starvation Risk',
  description: '4 processes; P1 has lowest priority and is nearly starved by P2/P3/P4.',
  traces: {
    Priority: [
      // Priority values: pid1=1(lowest), pid2=8, pid3=7, pid4=9(highest)
      { tick: 0,  algo: 'Priority', event: 'ARRIVE',   pid: 1, state: 'RUNNABLE', queue: 0, priority: 1 },
      { tick: 0,  algo: 'Priority', event: 'ARRIVE',   pid: 2, state: 'RUNNABLE', queue: 0, priority: 8 },
      { tick: 0,  algo: 'Priority', event: 'ARRIVE',   pid: 3, state: 'RUNNABLE', queue: 0, priority: 7 },
      { tick: 0,  algo: 'Priority', event: 'ARRIVE',   pid: 4, state: 'RUNNABLE', queue: 0, priority: 9 },
      { tick: 0,  algo: 'Priority', event: 'DISPATCH',  pid: 4, state: 'RUNNING',  queue: 0 },
      { tick: 8,  algo: 'Priority', event: 'EXIT',       pid: 4, state: 'ZOMBIE',   queue: 0, turnaround: 8,  waiting: 0, response: 0 },
      { tick: 8,  algo: 'Priority', event: 'DISPATCH',  pid: 2, state: 'RUNNING',  queue: 0 },
      { tick: 18, algo: 'Priority', event: 'EXIT',       pid: 2, state: 'ZOMBIE',   queue: 0, turnaround: 18, waiting: 8, response: 8 },
      { tick: 18, algo: 'Priority', event: 'DISPATCH',  pid: 3, state: 'RUNNING',  queue: 0 },
      { tick: 26, algo: 'Priority', event: 'EXIT',       pid: 3, state: 'ZOMBIE',   queue: 0, turnaround: 26, waiting: 18, response: 18 },
      // P1 has been waiting since tick 0; aging correction fires
      { tick: 28, algo: 'Priority', event: 'CORRECTION_APPLIED', pid: 1, state: 'RUNNABLE',
        correction_type: 'aging_activation', new_params: { aging_threshold: 20, boost_interval: 50 } },
      { tick: 28, algo: 'Priority', event: 'DISPATCH',  pid: 1, state: 'RUNNING',  queue: 0 },
      { tick: 38, algo: 'Priority', event: 'EXIT',       pid: 1, state: 'ZOMBIE',   queue: 0, turnaround: 38, waiting: 28, response: 28 },
    ],
  },
  recommendation: {
    recommended_scheduling_algorithm: 'Priority',
    params: { aging_threshold: 20, boost_interval: 50 },
    target_metric: 'avg_waiting_time',
    risks: ['starvation_low_priority'],
    reason: 'Wide priority spread detected. Priority scheduling with aging prevents P1 from being indefinitely blocked by higher-priority processes.',
    workload_interpretation: {
      workload_type: 'priority_mixed',
      main_risks: ['starvation'],
    },
    llm_model: 'solar-pro3',
    timestamp: '2026-05-22T12:00:00Z',
  },
  guardDecision: {
    guard_result: 'accepted',
    scheduling_algorithm: 'Priority',
    params: { aging_threshold: 20, boost_interval: 50 },
    reason: 'Priority with aging is implemented and parameters are in valid ranges.',
    original_recommendation: 'Priority',
    fallback_used: false,
  },
  metrics: {
    scheduling_algorithm: 'Priority',
    params: { aging_threshold: 20, boost_interval: 50 },
    process_count: 4,
    completed_count: 4,
    total_execution_time: 38,
    avg_response_time: 14.0,
    avg_turnaround_time: 22.5,
    avg_waiting_time: 13.5,
    throughput: 0.105,
    max_waiting_time: 28,
    starvation_occurred: true,
    starvation_pids: [1],
    preemption_count: 0,
    per_process: [
      { pid: 1, arrival_time: 0, first_run_time: 28, finish_time: 38, response_time: 28, turnaround_time: 38, waiting_time: 28 },
      { pid: 2, arrival_time: 0, first_run_time: 8,  finish_time: 18, response_time: 8,  turnaround_time: 18, waiting_time: 8  },
      { pid: 3, arrival_time: 0, first_run_time: 18, finish_time: 26, response_time: 18, turnaround_time: 26, waiting_time: 18 },
      { pid: 4, arrival_time: 0, first_run_time: 0,  finish_time: 8,  response_time: 0,  turnaround_time: 8,  waiting_time: 0  },
    ],
    comparison: {
      Priority: {
        avg_waiting_time: 13.5,
        avg_response_time: 14.0,
        avg_turnaround_time: 22.5,
        throughput: 0.105,
        max_waiting_time: 28,
        preemption_count: 0,
        starvation_occurred: true,
        burst_prediction_error: null,
        judgment: 'NEAR-SUCCESS',
      },
      RR: {
        avg_waiting_time: 10.5,
        avg_response_time: 1.0,
        avg_turnaround_time: 20.0,
        throughput: 0.105,
        max_waiting_time: 14,
        preemption_count: 18,
        starvation_occurred: false,
        burst_prediction_error: null,
        judgment: 'NEAR-SUCCESS',
      },
    },
    judgment: 'NEAR-SUCCESS',
    regret_score: 0.12,
    workload_file: 'workloads/starvation_risk.json',
  },
  workloadSummary: {
    process_count: 4,
    avg_arrival_gap: 0.0,
    cpu_bound_ratio: 0.75,
    interactive_ratio: 0.25,
    avg_priority: 6.25,
    priority_variance: 9.69,
    has_starvation_risk: true,
    burst_count_distribution: { min: 1, max: 1, avg: 1.0 },
    total_cpu_work: 36,
    workload_file: 'workloads/starvation_risk.json',
    workload_type: 'priority_mixed',
    target_metric: 'avg_waiting_time',
    main_risks: ['starvation'],
    reason: 'Large priority variance; P1 at priority 1 risks indefinite wait without aging.',
  },
  traceExplanation: {
    scheduling_algorithm: 'Priority',
    summary: 'Priority scheduling exposed a starvation risk for P1 (priority=1). Runtime aging correction was applied at tick 28 to unblock P1.',
    detected_pattern: 'starvation_detected',
    main_reason: 'P4 (priority=9), P2 (priority=8), and P3 (priority=7) were continuously preferred over P1 (priority=1). Without aging, P1 would never run.',
    evidence: [
      'P1 waited from tick 0 to tick 28 (28 ticks) — longest waiting_time in the trace.',
      'starvation_occurred = true, starvation_pids = [1].',
      'CORRECTION_APPLIED at tick 28: aging_threshold lowered to 20 to trigger P1 promotion.',
    ],
    suggestion: 'Set aging_threshold ≤ 20 for workloads with high priority variance to prevent future starvation.',
    runtime_corrections_applied: 1,
    llm_model: 'solar-pro3',
    timestamp: '2026-05-22T12:05:00Z',
  },
  ALGOS: ['Priority', 'RR'],
};

// ─────────────────────────────────────────────
// 4. many_processes — 8 processes, RR quantum=2
// ─────────────────────────────────────────────
export const many_processes = {
  label: 'Many Processes',
  description: '8 processes with RR quantum=2; stress-tests Gantt/lane rendering.',
  traces: {
    RR: [
      // Arrivals at ticks 0,2,3,5,6,8,10,12
      { tick: 0,  algo: 'RR', event: 'ARRIVE',   pid: 1, state: 'RUNNABLE', queue: 0, priority: 5 },
      { tick: 0,  algo: 'RR', event: 'DISPATCH',  pid: 1, state: 'RUNNING',  queue: 0 },
      { tick: 2,  algo: 'RR', event: 'ARRIVE',    pid: 2, state: 'RUNNABLE', queue: 0, priority: 5 },
      { tick: 2,  algo: 'RR', event: 'PREEMPT',   pid: 1, state: 'RUNNABLE', queue: 0, reason: 'quantum_expired' },
      { tick: 2,  algo: 'RR', event: 'DISPATCH',  pid: 2, state: 'RUNNING',  queue: 0 },
      { tick: 3,  algo: 'RR', event: 'ARRIVE',    pid: 3, state: 'RUNNABLE', queue: 0, priority: 5 },
      { tick: 4,  algo: 'RR', event: 'PREEMPT',   pid: 2, state: 'RUNNABLE', queue: 0, reason: 'quantum_expired' },
      { tick: 4,  algo: 'RR', event: 'DISPATCH',  pid: 1, state: 'RUNNING',  queue: 0 },
      { tick: 5,  algo: 'RR', event: 'ARRIVE',    pid: 4, state: 'RUNNABLE', queue: 0, priority: 5 },
      { tick: 6,  algo: 'RR', event: 'ARRIVE',    pid: 5, state: 'RUNNABLE', queue: 0, priority: 5 },
      { tick: 6,  algo: 'RR', event: 'PREEMPT',   pid: 1, state: 'RUNNABLE', queue: 0, reason: 'quantum_expired' },
      { tick: 6,  algo: 'RR', event: 'DISPATCH',  pid: 3, state: 'RUNNING',  queue: 0 },
      { tick: 8,  algo: 'RR', event: 'ARRIVE',    pid: 6, state: 'RUNNABLE', queue: 0, priority: 5 },
      { tick: 8,  algo: 'RR', event: 'PREEMPT',   pid: 3, state: 'RUNNABLE', queue: 0, reason: 'quantum_expired' },
      { tick: 8,  algo: 'RR', event: 'DISPATCH',  pid: 2, state: 'RUNNING',  queue: 0 },
      { tick: 10, algo: 'RR', event: 'ARRIVE',    pid: 7, state: 'RUNNABLE', queue: 0, priority: 5 },
      { tick: 10, algo: 'RR', event: 'PREEMPT',   pid: 2, state: 'RUNNABLE', queue: 0, reason: 'quantum_expired' },
      { tick: 10, algo: 'RR', event: 'DISPATCH',  pid: 4, state: 'RUNNING',  queue: 0 },
      { tick: 12, algo: 'RR', event: 'ARRIVE',    pid: 8, state: 'RUNNABLE', queue: 0, priority: 5 },
      { tick: 12, algo: 'RR', event: 'PREEMPT',   pid: 4, state: 'RUNNABLE', queue: 0, reason: 'quantum_expired' },
      { tick: 12, algo: 'RR', event: 'DISPATCH',  pid: 5, state: 'RUNNING',  queue: 0 },
      { tick: 14, algo: 'RR', event: 'PREEMPT',   pid: 5, state: 'RUNNABLE', queue: 0, reason: 'quantum_expired' },
      { tick: 14, algo: 'RR', event: 'DISPATCH',  pid: 6, state: 'RUNNING',  queue: 0 },
      { tick: 16, algo: 'RR', event: 'PREEMPT',   pid: 6, state: 'RUNNABLE', queue: 0, reason: 'quantum_expired' },
      { tick: 16, algo: 'RR', event: 'DISPATCH',  pid: 7, state: 'RUNNING',  queue: 0 },
      { tick: 18, algo: 'RR', event: 'PREEMPT',   pid: 7, state: 'RUNNABLE', queue: 0, reason: 'quantum_expired' },
      { tick: 18, algo: 'RR', event: 'DISPATCH',  pid: 8, state: 'RUNNING',  queue: 0 },
      { tick: 20, algo: 'RR', event: 'PREEMPT',   pid: 8, state: 'RUNNABLE', queue: 0, reason: 'quantum_expired' },
      { tick: 20, algo: 'RR', event: 'DISPATCH',  pid: 1, state: 'RUNNING',  queue: 0 },
      { tick: 22, algo: 'RR', event: 'EXIT',       pid: 1, state: 'ZOMBIE',   queue: 0, turnaround: 22, waiting: 14, response: 0 },
      { tick: 22, algo: 'RR', event: 'DISPATCH',  pid: 2, state: 'RUNNING',  queue: 0 },
      { tick: 24, algo: 'RR', event: 'EXIT',       pid: 2, state: 'ZOMBIE',   queue: 0, turnaround: 22, waiting: 14, response: 0 },
      { tick: 24, algo: 'RR', event: 'DISPATCH',  pid: 3, state: 'RUNNING',  queue: 0 },
      { tick: 26, algo: 'RR', event: 'EXIT',       pid: 3, state: 'ZOMBIE',   queue: 0, turnaround: 23, waiting: 17, response: 3 },
      { tick: 26, algo: 'RR', event: 'DISPATCH',  pid: 4, state: 'RUNNING',  queue: 0 },
      { tick: 28, algo: 'RR', event: 'EXIT',       pid: 4, state: 'ZOMBIE',   queue: 0, turnaround: 23, waiting: 17, response: 5 },
      { tick: 28, algo: 'RR', event: 'DISPATCH',  pid: 5, state: 'RUNNING',  queue: 0 },
      { tick: 30, algo: 'RR', event: 'EXIT',       pid: 5, state: 'ZOMBIE',   queue: 0, turnaround: 24, waiting: 18, response: 6 },
      { tick: 30, algo: 'RR', event: 'DISPATCH',  pid: 6, state: 'RUNNING',  queue: 0 },
      { tick: 32, algo: 'RR', event: 'EXIT',       pid: 6, state: 'ZOMBIE',   queue: 0, turnaround: 24, waiting: 18, response: 6 },
      { tick: 32, algo: 'RR', event: 'DISPATCH',  pid: 7, state: 'RUNNING',  queue: 0 },
      { tick: 34, algo: 'RR', event: 'EXIT',       pid: 7, state: 'ZOMBIE',   queue: 0, turnaround: 24, waiting: 18, response: 6 },
      { tick: 34, algo: 'RR', event: 'DISPATCH',  pid: 8, state: 'RUNNING',  queue: 0 },
      { tick: 36, algo: 'RR', event: 'EXIT',       pid: 8, state: 'ZOMBIE',   queue: 0, turnaround: 24, waiting: 18, response: 6 },
    ],
  },
  recommendation: {
    recommended_scheduling_algorithm: 'RR',
    params: { quantum: 2 },
    target_metric: 'avg_response_time',
    risks: ['high_context_switch_overhead'],
    reason: '8 short-lived processes benefit from fair time-sharing; RR with quantum=2 keeps response times low.',
    workload_interpretation: {
      workload_type: 'many_short_processes',
      main_risks: ['high_context_switch_overhead'],
    },
    llm_model: 'solar-pro3',
    timestamp: '2026-05-22T13:00:00Z',
  },
  guardDecision: {
    guard_result: 'accepted',
    scheduling_algorithm: 'RR',
    params: { quantum: 2 },
    reason: 'RR is implemented and quantum=2 is in the valid range [1, 100].',
    original_recommendation: 'RR',
    fallback_used: false,
  },
  metrics: {
    scheduling_algorithm: 'RR',
    params: { quantum: 2 },
    process_count: 8,
    completed_count: 8,
    total_execution_time: 36,
    avg_response_time: 4.6,
    avg_turnaround_time: 23.3,
    avg_waiting_time: 17.0,
    throughput: 0.222,
    max_waiting_time: 18,
    starvation_occurred: false,
    starvation_pids: [],
    preemption_count: 13,
    per_process: [
      { pid: 1, arrival_time: 0,  first_run_time: 0,  finish_time: 22, response_time: 0,  turnaround_time: 22, waiting_time: 14 },
      { pid: 2, arrival_time: 2,  first_run_time: 2,  finish_time: 24, response_time: 0,  turnaround_time: 22, waiting_time: 14 },
      { pid: 3, arrival_time: 3,  first_run_time: 6,  finish_time: 26, response_time: 3,  turnaround_time: 23, waiting_time: 17 },
      { pid: 4, arrival_time: 5,  first_run_time: 10, finish_time: 28, response_time: 5,  turnaround_time: 23, waiting_time: 17 },
      { pid: 5, arrival_time: 6,  first_run_time: 12, finish_time: 30, response_time: 6,  turnaround_time: 24, waiting_time: 18 },
      { pid: 6, arrival_time: 8,  first_run_time: 14, finish_time: 32, response_time: 6,  turnaround_time: 24, waiting_time: 18 },
      { pid: 7, arrival_time: 10, first_run_time: 16, finish_time: 34, response_time: 6,  turnaround_time: 24, waiting_time: 18 },
      { pid: 8, arrival_time: 12, first_run_time: 18, finish_time: 36, response_time: 6,  turnaround_time: 24, waiting_time: 18 },
    ],
    comparison: {
      RR: {
        avg_waiting_time: 17.0,
        avg_response_time: 4.6,
        avg_turnaround_time: 23.3,
        throughput: 0.222,
        max_waiting_time: 18,
        preemption_count: 13,
        starvation_occurred: false,
        burst_prediction_error: null,
        judgment: 'SUCCESS',
      },
    },
    judgment: 'SUCCESS',
    regret_score: 0.05,
    workload_file: 'workloads/many_processes.json',
  },
  workloadSummary: {
    process_count: 8,
    avg_arrival_gap: 1.7,
    cpu_bound_ratio: 0.5,
    interactive_ratio: 0.5,
    avg_priority: 5.0,
    priority_variance: 0.0,
    has_starvation_risk: false,
    burst_count_distribution: { min: 1, max: 1, avg: 1.0 },
    total_cpu_work: 32,
    workload_file: 'workloads/many_processes.json',
    workload_type: 'many_short_processes',
    target_metric: 'avg_response_time',
    main_risks: ['high_context_switch_overhead'],
    reason: '8 processes with uniform burst length; RR provides fair CPU sharing.',
  },
  traceExplanation: {
    scheduling_algorithm: 'RR',
    summary: 'RR handled 8 concurrent processes fairly with quantum=2, keeping max response time at 6 ticks.',
    detected_pattern: 'fair_sharing',
    main_reason: 'All 8 processes received equal time slices; no starvation occurred.',
    evidence: [
      '13 preemptions logged across 36 ticks.',
      'max_waiting_time = 18, uniform across later-arriving processes.',
      'No starvation_pids detected.',
    ],
    suggestion: 'Increasing quantum to 4 would reduce context switches at the cost of slightly higher response times.',
    runtime_corrections_applied: 0,
    llm_model: 'solar-pro3',
    timestamp: '2026-05-22T13:05:00Z',
  },
  ALGOS: ['RR'],
};

// ─────────────────────────────────────────────
// 5. long_trace — 50+ events, layout stress test
// ─────────────────────────────────────────────
export const long_trace = (() => {
  // Generate a long RR trace for 3 processes with burst 20 each, quantum=2
  // P1 arrives t=0, P2 arrives t=1, P3 arrives t=2
  const events = [];
  const pids = [1, 2, 3];
  const arrivals = [0, 1, 2];
  const bursts = { 1: 20, 2: 18, 3: 16 };
  const remaining = { 1: 20, 2: 18, 3: 16 };
  const firstRun = {};
  const priorities = { 1: 5, 2: 4, 3: 6 };
  const quantum = 2;

  // Arrivals
  arrivals.forEach((t, i) => {
    events.push({ tick: t, algo: 'RR', event: 'ARRIVE', pid: pids[i], state: 'RUNNABLE', queue: 0, priority: priorities[pids[i]] });
  });

  let tick = 0;
  let running = null;

  // Simple round-robin simulation
  const queue = [];
  const arrived = new Set();
  let done = new Set();

  // Seed initial arrivals at t=0
  pids.forEach((p, i) => { if (arrivals[i] === 0) queue.push(p); arrived.add(p); });

  const dispatch = (pid, t) => {
    if (firstRun[pid] === undefined) firstRun[pid] = t;
    events.push({ tick: t, algo: 'RR', event: 'DISPATCH', pid, state: 'RUNNING', queue: 0 });
    running = pid;
  };

  dispatch(queue.shift(), 0);
  let runStart = 0;

  for (tick = 1; tick <= 80 && done.size < 3; tick++) {
    // Check new arrivals
    pids.forEach((p, i) => {
      if (arrivals[i] === tick && !arrived.has(p)) {
        arrived.add(p);
        queue.push(p);
        events.push({ tick, algo: 'RR', event: 'ARRIVE', pid: p, state: 'RUNNABLE', queue: 0, priority: priorities[p] });
      }
    });

    remaining[running]--;

    if (remaining[running] === 0) {
      // Process exits
      const turnaround = tick - arrivals[pids.indexOf(running)];
      const waiting = turnaround - bursts[running];
      const response = (firstRun[running] || 0) - arrivals[pids.indexOf(running)];
      events.push({ tick, algo: 'RR', event: 'EXIT', pid: running, state: 'ZOMBIE', queue: 0,
        turnaround, waiting, response });
      done.add(running);
      running = null;

      if (queue.length > 0) {
        const next = queue.shift();
        dispatch(next, tick);
        runStart = tick;
      }
    } else if ((tick - runStart) >= quantum) {
      // Quantum expired
      events.push({ tick, algo: 'RR', event: 'PREEMPT', pid: running, state: 'RUNNABLE', queue: 0, reason: 'quantum_expired' });
      queue.push(running);
      const prev = running;
      running = null;

      if (queue.length > 0) {
        const next = queue.shift();
        dispatch(next, tick);
        runStart = tick;
      }
    }
  }

  const totalTime = Math.max(...events.map(e => e.tick), 1);

  return {
    label: 'Long Trace',
    description: `${events.length}+ events across 3 long-running processes; visual layout stress test.`,
    traces: { RR: events },
    recommendation: {
      recommended_scheduling_algorithm: 'RR',
      params: { quantum: 2 },
      target_metric: 'avg_response_time',
      risks: ['high_context_switch_overhead'],
      reason: 'Long CPU bursts with RR forces many preemptions; useful for testing trace rendering under load.',
      workload_interpretation: {
        workload_type: 'stress_test',
        main_risks: ['high_context_switch_overhead'],
      },
      llm_model: 'solar-pro3',
      timestamp: '2026-05-22T14:00:00Z',
    },
    guardDecision: {
      guard_result: 'accepted',
      scheduling_algorithm: 'RR',
      params: { quantum: 2 },
      reason: 'RR is implemented and quantum=2 is valid.',
      original_recommendation: 'RR',
      fallback_used: false,
    },
    metrics: {
      scheduling_algorithm: 'RR',
      params: { quantum: 2 },
      process_count: 3,
      completed_count: 3,
      total_execution_time: totalTime,
      avg_response_time: 1.0,
      avg_turnaround_time: totalTime / 3,
      avg_waiting_time: totalTime / 3 - 18,
      throughput: 3 / totalTime,
      max_waiting_time: totalTime - 16,
      starvation_occurred: false,
      starvation_pids: [],
      preemption_count: events.filter(e => e.event === 'PREEMPT').length,
      per_process: [
        { pid: 1, arrival_time: 0, first_run_time: 0,  finish_time: totalTime,     response_time: 0, turnaround_time: totalTime,     waiting_time: totalTime - 20     },
        { pid: 2, arrival_time: 1, first_run_time: 2,  finish_time: totalTime - 2, response_time: 1, turnaround_time: totalTime - 3, waiting_time: totalTime - 3 - 18 },
        { pid: 3, arrival_time: 2, first_run_time: 4,  finish_time: totalTime - 4, response_time: 2, turnaround_time: totalTime - 6, waiting_time: totalTime - 6 - 16 },
      ],
      comparison: {
        RR: {
          avg_waiting_time: totalTime / 3 - 18,
          avg_response_time: 1.0,
          avg_turnaround_time: totalTime / 3,
          throughput: 3 / totalTime,
          max_waiting_time: totalTime - 16,
          preemption_count: events.filter(e => e.event === 'PREEMPT').length,
          starvation_occurred: false,
          burst_prediction_error: null,
          judgment: 'SUCCESS',
        },
      },
      judgment: 'SUCCESS',
      regret_score: 0.0,
      workload_file: 'workloads/long_trace.json',
    },
    workloadSummary: {
      process_count: 3,
      avg_arrival_gap: 1.0,
      cpu_bound_ratio: 1.0,
      interactive_ratio: 0.0,
      avg_priority: 5.0,
      priority_variance: 0.67,
      has_starvation_risk: false,
      burst_count_distribution: { min: 16, max: 20, avg: 18.0 },
      total_cpu_work: 54,
      workload_file: 'workloads/long_trace.json',
      workload_type: 'stress_test',
      target_metric: 'avg_response_time',
      main_risks: ['high_context_switch_overhead'],
      reason: 'Long-burst processes stress-test the trace viewer with many preemption events.',
    },
    traceExplanation: {
      scheduling_algorithm: 'RR',
      summary: `Long-trace stress test generated ${events.length} events across 3 processes. RR produced many preemptions.`,
      detected_pattern: 'cpu_heavy_rr',
      main_reason: 'Long CPU bursts (16–20 ticks) with a short quantum (2) generate the maximum number of preemption events.',
      evidence: [
        `Total events: ${events.length}.`,
        `Preemption count: ${events.filter(e => e.event === 'PREEMPT').length}.`,
        'No starvation detected.',
      ],
      suggestion: 'This fixture is intended for layout/rendering stress tests, not scheduling quality evaluation.',
      runtime_corrections_applied: 0,
      llm_model: 'solar-pro3',
      timestamp: '2026-05-22T14:05:00Z',
    },
    ALGOS: ['RR'],
  };
})();

// ─────────────────────────────────────────────
// 6. missing_optional_fields — robustness / null-safety test
// ─────────────────────────────────────────────
export const missing_optional_fields = {
  label: 'Missing Optional Fields',
  description: 'Traces and metrics with optional fields omitted (null/undefined); tests UI null-safety.',
  traces: {
    RR: [
      // reason, queue, priority deliberately omitted
      { tick: 0,  algo: 'RR', event: 'ARRIVE',   pid: 1, state: 'RUNNABLE' },
      { tick: 0,  algo: 'RR', event: 'DISPATCH',  pid: 1, state: 'RUNNING' },
      { tick: 2,  algo: 'RR', event: 'ARRIVE',    pid: 2, state: 'RUNNABLE' },
      // PREEMPT with no reason field
      { tick: 4,  algo: 'RR', event: 'PREEMPT',   pid: 1, state: 'RUNNABLE' },
      { tick: 4,  algo: 'RR', event: 'DISPATCH',  pid: 2, state: 'RUNNING' },
      { tick: 5,  algo: 'RR', event: 'ARRIVE',    pid: 3, state: 'RUNNABLE' },
      { tick: 8,  algo: 'RR', event: 'PREEMPT',   pid: 2, state: 'RUNNABLE' },
      { tick: 8,  algo: 'RR', event: 'DISPATCH',  pid: 3, state: 'RUNNING' },
      // EXIT with null optional metrics
      { tick: 10, algo: 'RR', event: 'EXIT', pid: 3, state: 'ZOMBIE', turnaround: null, waiting: null, response: null },
      { tick: 10, algo: 'RR', event: 'DISPATCH', pid: 1, state: 'RUNNING' },
      { tick: 12, algo: 'RR', event: 'PREEMPT',   pid: 1, state: 'RUNNABLE' },
      { tick: 12, algo: 'RR', event: 'DISPATCH',  pid: 2, state: 'RUNNING' },
      { tick: 14, algo: 'RR', event: 'EXIT', pid: 2, state: 'ZOMBIE', turnaround: 12, waiting: undefined, response: 2 },
      { tick: 14, algo: 'RR', event: 'DISPATCH',  pid: 1, state: 'RUNNING' },
      { tick: 18, algo: 'RR', event: 'EXIT', pid: 1, state: 'ZOMBIE', turnaround: 18, waiting: 10, response: 0 },
    ],
  },
  recommendation: {
    recommended_scheduling_algorithm: 'RR',
    params: { quantum: 4 },
    // reason intentionally omitted
    target_metric: null,
    risks: [],
    workload_interpretation: null,
    llm_model: null,
    timestamp: null,
  },
  guardDecision: {
    guard_result: 'accepted',
    scheduling_algorithm: 'RR',
    params: { quantum: 4 },
    reason: null,
    original_recommendation: 'RR',
    fallback_used: false,
  },
  metrics: {
    scheduling_algorithm: 'RR',
    params: { quantum: 4 },
    process_count: 3,
    completed_count: 3,
    total_execution_time: 18,
    // Some aggregate metrics are null
    avg_response_time: null,
    avg_turnaround_time: null,
    avg_waiting_time: null,
    throughput: null,
    max_waiting_time: undefined,
    starvation_occurred: false,
    starvation_pids: null,
    preemption_count: 3,
    per_process: [
      { pid: 1, arrival_time: 0, first_run_time: 0,  finish_time: 18, response_time: 0,  turnaround_time: 18, waiting_time: 10 },
      // waiting_time null
      { pid: 2, arrival_time: 2, first_run_time: 4,  finish_time: 14, response_time: 2,  turnaround_time: 12, waiting_time: null },
      // turnaround_time and waiting_time undefined
      { pid: 3, arrival_time: 5, first_run_time: 8,  finish_time: 10, response_time: undefined, turnaround_time: undefined, waiting_time: undefined },
    ],
    // comparison intentionally omitted
    judgment: null,
    regret_score: null,
    workload_file: null,
  },
  workloadSummary: {
    process_count: 3,
    avg_arrival_gap: null,
    cpu_bound_ratio: null,
    interactive_ratio: null,
    avg_priority: null,
    priority_variance: null,
    has_starvation_risk: false,
    // burst_count_distribution omitted
    total_cpu_work: null,
    workload_file: null,
    workload_type: null,
    target_metric: null,
    main_risks: null,
    reason: undefined,
  },
  traceExplanation: {
    // scheduling_algorithm omitted
    summary: null,
    detected_pattern: undefined,
    main_reason: null,
    evidence: null,
    suggestion: undefined,
    runtime_corrections_applied: null,
    llm_model: null,
    timestamp: null,
  },
  ALGOS: ['RR'],
};

// ─────────────────────────────────────────────
// Exports
// ─────────────────────────────────────────────
export const FIXTURES = {
  interactive_heavy,
  cpu_bound,
  starvation_risk,
  many_processes,
  long_trace,
  missing_optional_fields,
};

export const FIXTURE_NAMES = Object.keys(FIXTURES);
