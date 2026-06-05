// Emergency fallback when live-data files are missing.
// Run scripts/run_live_dashboard_pipeline.py to generate real data.

export const fallbackManifest = {
  mode: 'fallback',
  updated_at: '1970-01-01T00:00:00Z',
  version: 0,
  workload: 'unknown',
  algorithms: ['RR', 'FCFS', 'Priority', 'MLFQ', 'SJF', 'SRTF'],
  recommended_algorithm: 'RR',
  target_metric: 'avg_response_time',
}

export const fallbackRecommendation = {
  recommended_scheduling_algorithm: 'RR',
  params: { quantum: 2 },
  target_metric: 'avg_response_time',
  risks: [],
  reason: 'Fallback: no live data. Run scripts/run_live_dashboard_pipeline.py.',
  workload_interpretation: { workload_type: 'unknown', main_risks: [] },
  llm_model: 'none',
  timestamp: '1970-01-01T00:00:00Z',
}

export const fallbackGuardDecision = {
  guard_result: 'accepted',
  scheduling_algorithm: 'RR',
  params: { quantum: 2 },
  reason: 'Fallback default.',
  original_recommendation: 'RR',
  fallback_used: true,
}

export const fallbackWorkloadSummary = {
  process_count: 0,
  workload_type: 'unknown',
  target_metric: 'avg_response_time',
  main_risks: [],
  reason: 'No live data.',
}

// No live data == no real run happened. Do NOT imply a failed execution:
// judgment is UNKNOWN (not FAIL), regret is null, and numeric metrics are null
// so the UI renders N/A instead of a misleading "0 / FAIL".
export const fallbackMetrics = {
  scheduling_algorithm: null,
  process_count: 0,
  completed_count: 0,
  total_execution_time: null,
  avg_response_time: null,
  avg_turnaround_time: null,
  avg_waiting_time: null,
  throughput: null,
  max_waiting_time: null,
  starvation_occurred: false,
  starvation_pids: [],
  preemption_count: null,
  per_process: [],
  comparison: {},
  judgment: 'UNKNOWN',
  regret_score: null,
  no_data: true,
}

export const fallbackTraces = {
  RR: [], FCFS: [], Priority: [], MLFQ: [], SJF: [], SRTF: [],
}
