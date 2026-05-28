// Auto-generated from outputs/_demo_fixtures/* — do not edit manually

export const recommendation = {
  "recommended_scheduling_algorithm": "MLFQ",
  "params": {
    "queues": 3,
    "quantum": [
      2,
      4,
      8
    ],
    "aging_threshold": 30,
    "boost_interval": 100
  },
  "target_metric": "avg_response_time",
  "risks": [
    "starvation_if_aging_too_weak"
  ],
  "reason": "The workload contains multiple short interactive jobs mixed with long CPU-bound jobs. MLFQ favors short jobs while still allowing CPU-bound jobs to make progress. RR would be fairer but slower for interactive jobs, and FCFS risks convoy effect.",
  "workload_interpretation": {
    "workload_type": "interactive_heavy",
    "main_risks": [
      "poor_response_time",
      "starvation"
    ]
  },
  "llm_model": "solar-pro3",
  "timestamp": "2026-05-22T10:00:00Z"
};

export const guardDecision = {
  "guard_result": "accepted",
  "scheduling_algorithm": "MLFQ",
  "params": {
    "queues": 3,
    "quantum": [
      2,
      4,
      8
    ],
    "aging_threshold": 30,
    "boost_interval": 100
  },
  "reason": "MLFQ is implemented and all parameters are in valid ranges.",
  "original_recommendation": "MLFQ",
  "fallback_used": false
};

export const metrics = {
  "scheduling_algorithm": "MLFQ",
  "params": {
    "queues": 3,
    "quantum": [
      2,
      4,
      8
    ],
    "aging_threshold": 30,
    "boost_interval": 100
  },
  "process_count": 5,
  "completed_count": 5,
  "total_execution_time": 56,
  "avg_response_time": 1.8,
  "avg_turnaround_time": 24.8,
  "avg_waiting_time": 14.8,
  "throughput": 0.089,
  "max_waiting_time": 38,
  "starvation_occurred": false,
  "starvation_pids": [],
  "preemption_count": 9,
  "per_process": [
    {
      "pid": 1,
      "arrival_time": 0,
      "first_run_time": 0,
      "finish_time": 56,
      "response_time": 0,
      "turnaround_time": 56,
      "waiting_time": 38
    },
    {
      "pid": 2,
      "arrival_time": 2,
      "first_run_time": 4,
      "finish_time": 24,
      "response_time": 2,
      "turnaround_time": 22,
      "waiting_time": 14
    },
    {
      "pid": 3,
      "arrival_time": 5,
      "first_run_time": 6,
      "finish_time": 8,
      "response_time": 1,
      "turnaround_time": 3,
      "waiting_time": 1
    },
    {
      "pid": 4,
      "arrival_time": 10,
      "first_run_time": 12,
      "finish_time": 48,
      "response_time": 2,
      "turnaround_time": 38,
      "waiting_time": 18
    },
    {
      "pid": 5,
      "arrival_time": 15,
      "first_run_time": 18,
      "finish_time": 20,
      "response_time": 3,
      "turnaround_time": 5,
      "waiting_time": 3
    }
  ],
  "comparison": {
    "RR": {
      "avg_waiting_time": 20.0,
      "avg_response_time": 3.2,
      "avg_turnaround_time": 30.0,
      "throughput": 0.1,
      "max_waiting_time": 32,
      "preemption_count": 10,
      "starvation_occurred": false,
      "burst_prediction_error": null,
      "judgment": "NEAR-SUCCESS"
    },
    "FCFS": {
      "avg_waiting_time": 18.4,
      "avg_response_time": 18.4,
      "avg_turnaround_time": 28.8,
      "throughput": 0.096,
      "max_waiting_time": 35,
      "preemption_count": 0,
      "starvation_occurred": false,
      "burst_prediction_error": null,
      "judgment": "FAIL"
    },
    "Priority": {
      "avg_waiting_time": 10.8,
      "avg_response_time": 8.4,
      "avg_turnaround_time": 21.2,
      "throughput": 0.104,
      "max_waiting_time": 22,
      "preemption_count": 2,
      "starvation_occurred": false,
      "burst_prediction_error": null,
      "judgment": "NEAR-SUCCESS"
    },
    "MLFQ": {
      "avg_waiting_time": 14.8,
      "avg_response_time": 1.8,
      "avg_turnaround_time": 24.8,
      "throughput": 0.089,
      "max_waiting_time": 38,
      "preemption_count": 9,
      "starvation_occurred": false,
      "burst_prediction_error": null,
      "judgment": "SUCCESS"
    },
    "SJF": {
      "avg_waiting_time": 12.4,
      "avg_response_time": 12.4,
      "avg_turnaround_time": 22.8,
      "throughput": 0.096,
      "max_waiting_time": 22,
      "preemption_count": 0,
      "starvation_occurred": false,
      "burst_prediction_error": 1.8,
      "judgment": "NEAR-SUCCESS"
    },
    "SRTF": {
      "avg_waiting_time": 7.0,
      "avg_response_time": 4.8,
      "avg_turnaround_time": 17.4,
      "throughput": 0.104,
      "max_waiting_time": 19,
      "preemption_count": 3,
      "starvation_occurred": false,
      "burst_prediction_error": 1.4,
      "judgment": "SUCCESS"
    }
  },
  "judgment": "SUCCESS",
  "regret_score": 0.07,
  "workload_file": "workloads/interactive_heavy.json"
};

export const workloadSummary = {
  "process_count": 5,
  "avg_arrival_gap": 3.0,
  "cpu_bound_ratio": 0.4,
  "interactive_ratio": 0.6,
  "avg_priority": 4.4,
  "priority_variance": 3.8,
  "has_starvation_risk": true,
  "burst_count_distribution": {
    "min": 1,
    "max": 4,
    "avg": 2.4
  },
  "total_cpu_work": 48,
  "workload_file": "workloads/interactive_heavy.json",
  "workload_type": "interactive_heavy",
  "target_metric": "avg_response_time",
  "main_risks": [
    "poor_response_time",
    "starvation"
  ],
  "reason": "The workload contains multiple short interactive jobs mixed with long CPU-bound jobs."
};

export const traceExplanation = {
  "scheduling_algorithm": "MLFQ",
  "summary": "MLFQ performed well on this interactive-heavy workload, achieving low average response time by quickly serving short interactive jobs while allowing CPU-bound jobs to make progress in lower-priority queues.",
  "detected_pattern": "interactive_favorable",
  "main_reason": "Short interactive jobs (P2, P3) received CPU time quickly due to MLFQ's highest-priority queue, while long CPU-bound jobs (P1, P4) were gradually demoted to lower queues.",
  "evidence": [
    "P2 (interactive) first ran at tick 2, response time = 2.",
    "P3 (interactive) first ran at tick 4, response time = 1.",
    "P1 (cpu_bound) was demoted from queue 0 to queue 1 at tick 10.",
    "Average response time 2.6 vs 12.0 for FCFS on the same workload.",
    "No starvation detected \u2014 aging promotion triggered for P4 at tick 80."
  ],
  "suggestion": "MLFQ parameters are well-tuned for this workload. Consider reducing aging_threshold to 20 if heavier CPU-bound jobs are added.",
  "runtime_corrections_applied": 1,
  "llm_model": "solar-pro3",
  "timestamp": "2026-05-22T10:05:00Z"
};

export const traces = {
  "RR": [
    {
      "tick": 0,
      "algo": "RR",
      "event": "ARRIVE",
      "pid": 1,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 5,
      "burst_hint": null
    },
    {
      "tick": 0,
      "algo": "RR",
      "event": "DISPATCH",
      "pid": 1,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 2,
      "algo": "RR",
      "event": "ARRIVE",
      "pid": 2,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 2,
      "burst_hint": null
    },
    {
      "tick": 4,
      "algo": "RR",
      "event": "PREEMPT",
      "pid": 1,
      "state": "RUNNABLE",
      "queue": 0,
      "reason": "quantum_expired"
    },
    {
      "tick": 4,
      "algo": "RR",
      "event": "DISPATCH",
      "pid": 2,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 5,
      "algo": "RR",
      "event": "ARRIVE",
      "pid": 3,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 3,
      "burst_hint": null
    },
    {
      "tick": 8,
      "algo": "RR",
      "event": "PREEMPT",
      "pid": 2,
      "state": "RUNNABLE",
      "queue": 0,
      "reason": "quantum_expired"
    },
    {
      "tick": 8,
      "algo": "RR",
      "event": "DISPATCH",
      "pid": 3,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 10,
      "algo": "RR",
      "event": "ARRIVE",
      "pid": 4,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 7,
      "burst_hint": null
    },
    {
      "tick": 12,
      "algo": "RR",
      "event": "PREEMPT",
      "pid": 3,
      "state": "RUNNABLE",
      "queue": 0,
      "reason": "quantum_expired"
    },
    {
      "tick": 12,
      "algo": "RR",
      "event": "DISPATCH",
      "pid": 1,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 15,
      "algo": "RR",
      "event": "ARRIVE",
      "pid": 5,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 4,
      "burst_hint": null
    },
    {
      "tick": 16,
      "algo": "RR",
      "event": "PREEMPT",
      "pid": 1,
      "state": "RUNNABLE",
      "queue": 0,
      "reason": "quantum_expired"
    },
    {
      "tick": 16,
      "algo": "RR",
      "event": "DISPATCH",
      "pid": 4,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 20,
      "algo": "RR",
      "event": "PREEMPT",
      "pid": 4,
      "state": "RUNNABLE",
      "queue": 0,
      "reason": "quantum_expired"
    },
    {
      "tick": 20,
      "algo": "RR",
      "event": "DISPATCH",
      "pid": 5,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 22,
      "algo": "RR",
      "event": "EXIT",
      "pid": 5,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 7,
      "waiting": 5,
      "response": 5
    },
    {
      "tick": 22,
      "algo": "RR",
      "event": "DISPATCH",
      "pid": 2,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 26,
      "algo": "RR",
      "event": "PREEMPT",
      "pid": 2,
      "state": "RUNNABLE",
      "queue": 0,
      "reason": "quantum_expired"
    },
    {
      "tick": 26,
      "algo": "RR",
      "event": "DISPATCH",
      "pid": 3,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 28,
      "algo": "RR",
      "event": "EXIT",
      "pid": 3,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 23,
      "waiting": 19,
      "response": 3
    },
    {
      "tick": 28,
      "algo": "RR",
      "event": "DISPATCH",
      "pid": 1,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 32,
      "algo": "RR",
      "event": "PREEMPT",
      "pid": 1,
      "state": "RUNNABLE",
      "queue": 0,
      "reason": "quantum_expired"
    },
    {
      "tick": 32,
      "algo": "RR",
      "event": "DISPATCH",
      "pid": 4,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 36,
      "algo": "RR",
      "event": "PREEMPT",
      "pid": 4,
      "state": "RUNNABLE",
      "queue": 0,
      "reason": "quantum_expired"
    },
    {
      "tick": 36,
      "algo": "RR",
      "event": "DISPATCH",
      "pid": 2,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 38,
      "algo": "RR",
      "event": "EXIT",
      "pid": 2,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 36,
      "waiting": 28,
      "response": 2
    },
    {
      "tick": 38,
      "algo": "RR",
      "event": "DISPATCH",
      "pid": 1,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 42,
      "algo": "RR",
      "event": "PREEMPT",
      "pid": 1,
      "state": "RUNNABLE",
      "queue": 0,
      "reason": "quantum_expired"
    },
    {
      "tick": 42,
      "algo": "RR",
      "event": "DISPATCH",
      "pid": 4,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 46,
      "algo": "RR",
      "event": "EXIT",
      "pid": 4,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 36,
      "waiting": 16,
      "response": 6
    },
    {
      "tick": 46,
      "algo": "RR",
      "event": "DISPATCH",
      "pid": 1,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 50,
      "algo": "RR",
      "event": "EXIT",
      "pid": 1,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 50,
      "waiting": 32,
      "response": 0
    }
  ],
  "FCFS": [
    {
      "tick": 0,
      "algo": "FCFS",
      "event": "ARRIVE",
      "pid": 1,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 5,
      "burst_hint": null
    },
    {
      "tick": 0,
      "algo": "FCFS",
      "event": "DISPATCH",
      "pid": 1,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 2,
      "algo": "FCFS",
      "event": "ARRIVE",
      "pid": 2,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 2,
      "burst_hint": null
    },
    {
      "tick": 5,
      "algo": "FCFS",
      "event": "ARRIVE",
      "pid": 3,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 3,
      "burst_hint": null
    },
    {
      "tick": 10,
      "algo": "FCFS",
      "event": "ARRIVE",
      "pid": 4,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 7,
      "burst_hint": null
    },
    {
      "tick": 15,
      "algo": "FCFS",
      "event": "ARRIVE",
      "pid": 5,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 4,
      "burst_hint": null
    },
    {
      "tick": 18,
      "algo": "FCFS",
      "event": "EXIT",
      "pid": 1,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 18,
      "waiting": 0,
      "response": 0
    },
    {
      "tick": 18,
      "algo": "FCFS",
      "event": "DISPATCH",
      "pid": 2,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 26,
      "algo": "FCFS",
      "event": "EXIT",
      "pid": 2,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 24,
      "waiting": 16,
      "response": 16
    },
    {
      "tick": 26,
      "algo": "FCFS",
      "event": "DISPATCH",
      "pid": 3,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 30,
      "algo": "FCFS",
      "event": "EXIT",
      "pid": 3,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 25,
      "waiting": 21,
      "response": 21
    },
    {
      "tick": 30,
      "algo": "FCFS",
      "event": "DISPATCH",
      "pid": 4,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 50,
      "algo": "FCFS",
      "event": "EXIT",
      "pid": 4,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 40,
      "waiting": 20,
      "response": 20
    },
    {
      "tick": 50,
      "algo": "FCFS",
      "event": "DISPATCH",
      "pid": 5,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 52,
      "algo": "FCFS",
      "event": "EXIT",
      "pid": 5,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 37,
      "waiting": 35,
      "response": 35
    }
  ],
  "PRIORITY": [
    {
      "tick": 0,
      "algo": "Priority",
      "event": "ARRIVE",
      "pid": 1,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 5,
      "burst_hint": null
    },
    {
      "tick": 0,
      "algo": "Priority",
      "event": "DISPATCH",
      "pid": 1,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 2,
      "algo": "Priority",
      "event": "ARRIVE",
      "pid": 2,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 2,
      "burst_hint": null
    },
    {
      "tick": 2,
      "algo": "Priority",
      "event": "PREEMPT",
      "pid": 1,
      "state": "RUNNABLE",
      "queue": 0,
      "reason": "higher_priority_arrived"
    },
    {
      "tick": 2,
      "algo": "Priority",
      "event": "DISPATCH",
      "pid": 2,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 5,
      "algo": "Priority",
      "event": "ARRIVE",
      "pid": 3,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 3,
      "burst_hint": null
    },
    {
      "tick": 10,
      "algo": "Priority",
      "event": "EXIT",
      "pid": 2,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 8,
      "waiting": 0,
      "response": 0
    },
    {
      "tick": 10,
      "algo": "Priority",
      "event": "ARRIVE",
      "pid": 4,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 7,
      "burst_hint": null
    },
    {
      "tick": 10,
      "algo": "Priority",
      "event": "DISPATCH",
      "pid": 3,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 14,
      "algo": "Priority",
      "event": "EXIT",
      "pid": 3,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 9,
      "waiting": 5,
      "response": 5
    },
    {
      "tick": 14,
      "algo": "Priority",
      "event": "DISPATCH",
      "pid": 1,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 15,
      "algo": "Priority",
      "event": "ARRIVE",
      "pid": 5,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 4,
      "burst_hint": null
    },
    {
      "tick": 30,
      "algo": "Priority",
      "event": "EXIT",
      "pid": 1,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 30,
      "waiting": 12,
      "response": 0
    },
    {
      "tick": 30,
      "algo": "Priority",
      "event": "DISPATCH",
      "pid": 5,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 32,
      "algo": "Priority",
      "event": "EXIT",
      "pid": 5,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 17,
      "waiting": 15,
      "response": 15
    },
    {
      "tick": 32,
      "algo": "Priority",
      "event": "DISPATCH",
      "pid": 4,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 52,
      "algo": "Priority",
      "event": "EXIT",
      "pid": 4,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 42,
      "waiting": 22,
      "response": 22
    }
  ],
  "MLFQ": [
    {
      "tick": 0,
      "algo": "MLFQ",
      "event": "ARRIVE",
      "pid": 1,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 5,
      "burst_hint": null
    },
    {
      "tick": 0,
      "algo": "MLFQ",
      "event": "DISPATCH",
      "pid": 1,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 2,
      "algo": "MLFQ",
      "event": "ARRIVE",
      "pid": 2,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 2,
      "burst_hint": null
    },
    {
      "tick": 2,
      "algo": "MLFQ",
      "event": "PREEMPT",
      "pid": 1,
      "state": "RUNNABLE",
      "queue": 0,
      "reason": "quantum_expired"
    },
    {
      "tick": 2,
      "algo": "MLFQ",
      "event": "DISPATCH",
      "pid": 2,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 4,
      "algo": "MLFQ",
      "event": "PREEMPT",
      "pid": 2,
      "state": "RUNNABLE",
      "queue": 1,
      "reason": "quantum_expired"
    },
    {
      "tick": 4,
      "algo": "MLFQ",
      "event": "QUEUE_CHANGE",
      "pid": 2,
      "state": "RUNNABLE",
      "from_queue": 0,
      "to_queue": 1,
      "reason": "demotion"
    },
    {
      "tick": 4,
      "algo": "MLFQ",
      "event": "DISPATCH",
      "pid": 1,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 5,
      "algo": "MLFQ",
      "event": "ARRIVE",
      "pid": 3,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 3,
      "burst_hint": null
    },
    {
      "tick": 6,
      "algo": "MLFQ",
      "event": "PREEMPT",
      "pid": 1,
      "state": "RUNNABLE",
      "queue": 1,
      "reason": "quantum_expired"
    },
    {
      "tick": 6,
      "algo": "MLFQ",
      "event": "QUEUE_CHANGE",
      "pid": 1,
      "state": "RUNNABLE",
      "from_queue": 0,
      "to_queue": 1,
      "reason": "demotion"
    },
    {
      "tick": 6,
      "algo": "MLFQ",
      "event": "DISPATCH",
      "pid": 3,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 8,
      "algo": "MLFQ",
      "event": "EXIT",
      "pid": 3,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 3,
      "waiting": 1,
      "response": 1
    },
    {
      "tick": 8,
      "algo": "MLFQ",
      "event": "DISPATCH",
      "pid": 2,
      "state": "RUNNING",
      "queue": 1
    },
    {
      "tick": 10,
      "algo": "MLFQ",
      "event": "ARRIVE",
      "pid": 4,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 7,
      "burst_hint": null
    },
    {
      "tick": 12,
      "algo": "MLFQ",
      "event": "PREEMPT",
      "pid": 2,
      "state": "RUNNABLE",
      "queue": 1,
      "reason": "quantum_expired"
    },
    {
      "tick": 12,
      "algo": "MLFQ",
      "event": "DISPATCH",
      "pid": 4,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 14,
      "algo": "MLFQ",
      "event": "PREEMPT",
      "pid": 4,
      "state": "RUNNABLE",
      "queue": 1,
      "reason": "quantum_expired"
    },
    {
      "tick": 14,
      "algo": "MLFQ",
      "event": "QUEUE_CHANGE",
      "pid": 4,
      "state": "RUNNABLE",
      "from_queue": 0,
      "to_queue": 1,
      "reason": "demotion"
    },
    {
      "tick": 14,
      "algo": "MLFQ",
      "event": "DISPATCH",
      "pid": 1,
      "state": "RUNNING",
      "queue": 1
    },
    {
      "tick": 15,
      "algo": "MLFQ",
      "event": "ARRIVE",
      "pid": 5,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 4,
      "burst_hint": null
    },
    {
      "tick": 18,
      "algo": "MLFQ",
      "event": "PREEMPT",
      "pid": 1,
      "state": "RUNNABLE",
      "queue": 1,
      "reason": "quantum_expired"
    },
    {
      "tick": 18,
      "algo": "MLFQ",
      "event": "DISPATCH",
      "pid": 5,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 20,
      "algo": "MLFQ",
      "event": "EXIT",
      "pid": 5,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 5,
      "waiting": 3,
      "response": 3
    },
    {
      "tick": 20,
      "algo": "MLFQ",
      "event": "DISPATCH",
      "pid": 2,
      "state": "RUNNING",
      "queue": 1
    },
    {
      "tick": 24,
      "algo": "MLFQ",
      "event": "EXIT",
      "pid": 2,
      "state": "ZOMBIE",
      "queue": 1,
      "turnaround": 22,
      "waiting": 14,
      "response": 2
    },
    {
      "tick": 24,
      "algo": "MLFQ",
      "event": "DISPATCH",
      "pid": 4,
      "state": "RUNNING",
      "queue": 1
    },
    {
      "tick": 28,
      "algo": "MLFQ",
      "event": "PREEMPT",
      "pid": 4,
      "state": "RUNNABLE",
      "queue": 2,
      "reason": "quantum_expired"
    },
    {
      "tick": 28,
      "algo": "MLFQ",
      "event": "QUEUE_CHANGE",
      "pid": 4,
      "state": "RUNNABLE",
      "from_queue": 1,
      "to_queue": 2,
      "reason": "demotion"
    },
    {
      "tick": 28,
      "algo": "MLFQ",
      "event": "DISPATCH",
      "pid": 1,
      "state": "RUNNING",
      "queue": 1
    },
    {
      "tick": 32,
      "algo": "MLFQ",
      "event": "PREEMPT",
      "pid": 1,
      "state": "RUNNABLE",
      "queue": 2,
      "reason": "quantum_expired"
    },
    {
      "tick": 32,
      "algo": "MLFQ",
      "event": "QUEUE_CHANGE",
      "pid": 1,
      "state": "RUNNABLE",
      "from_queue": 1,
      "to_queue": 2,
      "reason": "demotion"
    },
    {
      "tick": 32,
      "algo": "MLFQ",
      "event": "DISPATCH",
      "pid": 4,
      "state": "RUNNING",
      "queue": 2
    },
    {
      "tick": 45,
      "algo": "MLFQ",
      "event": "CORRECTION_APPLIED",
      "pid": -1,
      "state": null,
      "correction_type": "parameter_update",
      "new_params": {
        "aging_threshold": 20,
        "boost_interval": 80
      }
    },
    {
      "tick": 48,
      "algo": "MLFQ",
      "event": "EXIT",
      "pid": 4,
      "state": "ZOMBIE",
      "queue": 2,
      "turnaround": 38,
      "waiting": 18,
      "response": 2
    },
    {
      "tick": 48,
      "algo": "MLFQ",
      "event": "DISPATCH",
      "pid": 1,
      "state": "RUNNING",
      "queue": 2
    },
    {
      "tick": 56,
      "algo": "MLFQ",
      "event": "EXIT",
      "pid": 1,
      "state": "ZOMBIE",
      "queue": 2,
      "turnaround": 56,
      "waiting": 38,
      "response": 0
    }
  ],
  "SJF": [
    {
      "tick": 0,
      "algo": "SJF",
      "event": "ARRIVE",
      "pid": 1,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 5,
      "burst_hint": null
    },
    {
      "tick": 0,
      "algo": "SJF",
      "event": "DISPATCH",
      "pid": 1,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 2,
      "algo": "SJF",
      "event": "ARRIVE",
      "pid": 2,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 2,
      "burst_hint": null
    },
    {
      "tick": 5,
      "algo": "SJF",
      "event": "ARRIVE",
      "pid": 3,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 3,
      "burst_hint": null
    },
    {
      "tick": 10,
      "algo": "SJF",
      "event": "ARRIVE",
      "pid": 4,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 7,
      "burst_hint": null
    },
    {
      "tick": 15,
      "algo": "SJF",
      "event": "ARRIVE",
      "pid": 5,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 4,
      "burst_hint": null
    },
    {
      "tick": 18,
      "algo": "SJF",
      "event": "EXIT",
      "pid": 1,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 18,
      "waiting": 0,
      "response": 0
    },
    {
      "tick": 18,
      "algo": "SJF",
      "event": "DISPATCH",
      "pid": 5,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 20,
      "algo": "SJF",
      "event": "EXIT",
      "pid": 5,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 5,
      "waiting": 3,
      "response": 3
    },
    {
      "tick": 20,
      "algo": "SJF",
      "event": "DISPATCH",
      "pid": 3,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 24,
      "algo": "SJF",
      "event": "EXIT",
      "pid": 3,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 19,
      "waiting": 15,
      "response": 15
    },
    {
      "tick": 24,
      "algo": "SJF",
      "event": "DISPATCH",
      "pid": 2,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 32,
      "algo": "SJF",
      "event": "EXIT",
      "pid": 2,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 30,
      "waiting": 22,
      "response": 22
    },
    {
      "tick": 32,
      "algo": "SJF",
      "event": "DISPATCH",
      "pid": 4,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 52,
      "algo": "SJF",
      "event": "EXIT",
      "pid": 4,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 42,
      "waiting": 22,
      "response": 22
    }
  ],
  "SRTF": [
    {
      "tick": 0,
      "algo": "SRTF",
      "event": "ARRIVE",
      "pid": 1,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 5,
      "burst_hint": null
    },
    {
      "tick": 0,
      "algo": "SRTF",
      "event": "DISPATCH",
      "pid": 1,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 2,
      "algo": "SRTF",
      "event": "ARRIVE",
      "pid": 2,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 2,
      "burst_hint": null
    },
    {
      "tick": 2,
      "algo": "SRTF",
      "event": "PREEMPT",
      "pid": 1,
      "state": "RUNNABLE",
      "queue": 0,
      "reason": "higher_priority_arrived"
    },
    {
      "tick": 2,
      "algo": "SRTF",
      "event": "DISPATCH",
      "pid": 2,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 5,
      "algo": "SRTF",
      "event": "ARRIVE",
      "pid": 3,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 3,
      "burst_hint": null
    },
    {
      "tick": 10,
      "algo": "SRTF",
      "event": "ARRIVE",
      "pid": 4,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 7,
      "burst_hint": null
    },
    {
      "tick": 10,
      "algo": "SRTF",
      "event": "EXIT",
      "pid": 2,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 8,
      "waiting": 0,
      "response": 0
    },
    {
      "tick": 10,
      "algo": "SRTF",
      "event": "DISPATCH",
      "pid": 3,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 14,
      "algo": "SRTF",
      "event": "EXIT",
      "pid": 3,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 9,
      "waiting": 5,
      "response": 5
    },
    {
      "tick": 14,
      "algo": "SRTF",
      "event": "DISPATCH",
      "pid": 1,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 15,
      "algo": "SRTF",
      "event": "ARRIVE",
      "pid": 5,
      "state": "RUNNABLE",
      "queue": 0,
      "priority": 4,
      "burst_hint": null
    },
    {
      "tick": 15,
      "algo": "SRTF",
      "event": "PREEMPT",
      "pid": 1,
      "state": "RUNNABLE",
      "queue": 0,
      "reason": "higher_priority_arrived"
    },
    {
      "tick": 15,
      "algo": "SRTF",
      "event": "DISPATCH",
      "pid": 5,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 17,
      "algo": "SRTF",
      "event": "EXIT",
      "pid": 5,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 2,
      "waiting": 0,
      "response": 0
    },
    {
      "tick": 17,
      "algo": "SRTF",
      "event": "DISPATCH",
      "pid": 1,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 29,
      "algo": "SRTF",
      "event": "EXIT",
      "pid": 1,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 29,
      "waiting": 11,
      "response": 0
    },
    {
      "tick": 29,
      "algo": "SRTF",
      "event": "DISPATCH",
      "pid": 4,
      "state": "RUNNING",
      "queue": 0
    },
    {
      "tick": 49,
      "algo": "SRTF",
      "event": "EXIT",
      "pid": 4,
      "state": "ZOMBIE",
      "queue": 0,
      "turnaround": 39,
      "waiting": 19,
      "response": 19
    }
  ]
};

export const ALGOS = ['RR', 'FCFS', 'Priority', 'MLFQ', 'SJF', 'SRTF'];

export const PROC_COLORS = {
  1: '#6366f1',
  2: '#f43f5e',
  3: '#10b981',
  4: '#8b5cf6',
  5: '#f59e0b',
  6: '#0ea5e9',
};

export const ALGO_COLORS = {
  RR:       '#6366f1',
  FCFS:     '#f43f5e',
  Priority: '#10b981',
  MLFQ:     '#8b5cf6',
  SJF:      '#f59e0b',
  SRTF:     '#0ea5e9',
};
