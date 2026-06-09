// Backward-compatible schema readers + metric-aware judgment for the dashboard.
export const CANONICAL_ALGOS = ['RR', 'FCFS', 'Priority', 'MLFQ', 'SJF', 'SRTF']

const ALGO_DISPLAY = { RR: 'RR', FCFS: 'FCFS', PRIORITY: 'Priority', MLFQ: 'MLFQ', SJF: 'SJF', SRTF: 'SRTF' }

export function normalizeAlgo(name) {
  if (!name) return 'RR'
  const key = String(name).trim().toUpperCase()
  return ALGO_DISPLAY[key] || String(name).trim()
}

const METRIC_ALIASES = {
  response_time: 'avg_response_time',
  waiting_time: 'avg_waiting_time',
  turnaround_time: 'avg_turnaround_time',
  avg_response_time: 'avg_response_time',
  avg_waiting_time: 'avg_waiting_time',
  avg_turnaround_time: 'avg_turnaround_time',
  throughput: 'throughput',
  max_waiting_time: 'max_waiting_time',
  preemption_count: 'preemption_count',
  starvation: 'starvation_occurred',
  starvation_occurred: 'starvation_occurred',
  fairness: 'fairness',
}

export function normalizeTargetMetric(metric) {
  if (!metric) return 'avg_response_time'
  const key = String(metric).trim().toLowerCase()
  return METRIC_ALIASES[key] || key
}

const HIGHER_BETTER = new Set(['throughput'])
const LOWER_BETTER = new Set([
  'avg_response_time', 'avg_waiting_time', 'avg_turnaround_time',
  'max_waiting_time', 'preemption_count',
])

export function isHigherBetterMetric(metric) { return HIGHER_BETTER.has(normalizeTargetMetric(metric)) }
export function isLowerBetterMetric(metric) { return LOWER_BETTER.has(normalizeTargetMetric(metric)) }

export function getRecommendedAlgorithm(rec, fallback = 'RR') {
  if (!rec) return fallback
  return normalizeAlgo(rec.recommended_scheduling_algorithm || rec.algorithm || fallback)
}

export function getGuardAlgorithm(guard, rec = null, fallback = 'RR') {
  if (guard) {
    const a = guard.scheduling_algorithm || guard.algorithm
    if (a) return normalizeAlgo(a)
    if (guard.fallback_used && guard.fallback_algorithm) return normalizeAlgo(guard.fallback_algorithm)
  }
  if (rec) return getRecommendedAlgorithm(rec, fallback)
  return fallback
}

export function getEventTick(ev) {
  if (!ev) return null
  if (ev.tick !== undefined && ev.tick !== null) return ev.tick
  if (ev.time !== undefined && ev.time !== null) return ev.time
  return null
}

export function getEventAlgo(ev) {
  if (!ev) return null
  const a = ev.algo || ev.algorithm
  return a ? normalizeAlgo(a) : null
}

export function normalizeTraceEvent(ev, defaultAlgo = null) {
  if (!ev || typeof ev !== 'object') return ev
  const out = { ...ev }
  const tick = getEventTick(ev)
  if (tick !== null) out.tick = tick
  const algo = getEventAlgo(ev) || (defaultAlgo ? normalizeAlgo(defaultAlgo) : undefined)
  if (algo) out.algo = algo
  return out
}

const METRIC_KEYS = {
  avg_response_time: 'avg_response_time',
  avg_waiting_time: 'avg_waiting_time',
  avg_turnaround_time: 'avg_turnaround_time',
  throughput: 'throughput',
  max_waiting_time: 'max_waiting_time',
  preemption_count: 'preemption_count',
}

// Sub-tick absolute floor for the regret denominator. Mirrors the same floor
// in scripts/orchestrator.py:_judge. xv6 traces are tick-granular and very
// short, so when best≈0 a relative-only delta blows up: e.g. FCFS at
// avg_response_time=0.2 vs MLFQ=0.0 is sub-tick rounding, not a regression.
// On simulator traces (waits in tens of ticks) this floor is dwarfed and has
// no practical effect.
const JUDGMENT_ABS_FLOOR = 0.5

// Metric-aware judgment for ONE algorithm row vs the whole comparison set.
export function computeAlgorithmJudgment(algoMetrics, allComparisonMetrics, targetMetric) {
  if (!algoMetrics) return 'UNKNOWN'
  if (algoMetrics.starvation_occurred === true) return 'FAIL'
  const metric = normalizeTargetMetric(targetMetric)
  const key = METRIC_KEYS[metric]
  if (!key) return 'UNKNOWN'
  const value = algoMetrics[key]
  if (typeof value !== 'number') return 'UNKNOWN'
  const vals = (allComparisonMetrics || []).map(m => m && m[key]).filter(v => typeof v === 'number')
  if (!vals.length) return 'UNKNOWN'
  const higher = isHigherBetterMetric(metric)
  const best = higher ? Math.max(...vals) : Math.min(...vals)
  // Sub-tick noise: tick-granular metrics within the absolute floor of the
  // best are SUCCESS. Throughput is dimensionless, so the floor is skipped.
  if (key !== 'throughput' && Math.abs(value - best) <= JUDGMENT_ABS_FLOOR) {
    return 'SUCCESS'
  }
  const denom = Math.max(Math.abs(best), JUDGMENT_ABS_FLOOR)
  const regret = higher ? (best - value) / denom : (value - best) / denom
  // Thresholds mirror tools/metrics.py {SUCCESS_REGRET, NEAR_SUCCESS_REGRET}.
  // Updated 2026-05-28: NEAR tightened 0.30 -> 0.25 per overnight work plan §5.
  if (regret <= 0.10) return 'SUCCESS'
  if (regret <= 0.25) return 'NEAR-SUCCESS'
  return 'FAIL'
}

// Best algorithm per canonical metric, computed from a metrics.comparison
// block. Skips entries that report starvation_occurred=true (they cannot
// be the "best" pick — mirrors the existing Judge rule).
//
// Returns { metric: { algo, value, higher_better } } for every metric in
// METRIC_KEYS where at least one non-starving candidate has a numeric value.
// Metrics with no candidates are omitted. preemption_count is intentionally
// included so callers can choose to display or skip it.
export function computeBestPerMetric(comparison) {
  if (!comparison || typeof comparison !== 'object') return {}
  const out = {}
  for (const key of Object.values(METRIC_KEYS)) {
    const higher = isHigherBetterMetric(key)
    let bestAlgo = null
    let bestVal = higher ? -Infinity : Infinity
    for (const [algo, row] of Object.entries(comparison)) {
      if (!row || typeof row !== 'object') continue
      if (row.starvation_occurred === true) continue
      const v = row[key]
      if (typeof v !== 'number') continue
      if (higher ? v > bestVal : v < bestVal) {
        bestAlgo = algo
        bestVal = v
      }
    }
    if (bestAlgo !== null) {
      out[key] = { algo: bestAlgo, value: bestVal, higher_better: higher }
    }
  }
  return out
}

// The simulator backend was removed: only data that EXPLICITLY claims
// "simulator" (legacy snapshots) is reported as such; an empty/unknown
// manifest must read as 'unknown', never default to a backend that no
// longer exists (it would falsely badge stale data as a simulator run).
export function getBackend(manifest) {
  if (!manifest) return 'unknown'
  if (manifest.backend) {
    const b = String(manifest.backend).toLowerCase()
    if (b === 'xv6' || b === 'xv6-log') return 'xv6'
    if (b === 'fallback') return 'fallback'
    if (b === 'simulator') return 'simulator'
    return 'unknown'
  }
  const mode = String(manifest.mode || '').toLowerCase()
  if (mode === 'xv6-log' || mode === 'xv6') return 'xv6'
  if (mode === 'fallback') return 'fallback'
  if (mode === 'simulator') return 'simulator'
  return 'unknown'
}
