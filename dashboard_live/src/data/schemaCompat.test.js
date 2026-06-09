import { describe, it, expect } from 'vitest'
import {
  normalizeAlgo, normalizeTargetMetric,
  isHigherBetterMetric, isLowerBetterMetric,
  getGuardAlgorithm, getRecommendedAlgorithm,
  computeAlgorithmJudgment, computeBestPerMetric, getBackend,
} from './schemaCompat.js'

describe('normalizeAlgo', () => {
  it('maps case-insensitive spellings to canonical display names', () => {
    expect(normalizeAlgo('priority')).toBe('Priority')
    expect(normalizeAlgo('MLFQ')).toBe('MLFQ')
    expect(normalizeAlgo('srtf')).toBe('SRTF')
  })
  it('defaults to RR on empty input', () => {
    expect(normalizeAlgo(null)).toBe('RR')
    expect(normalizeAlgo('')).toBe('RR')
  })
})

describe('normalizeTargetMetric', () => {
  it('aliases short metric names to the avg_ canonical form', () => {
    expect(normalizeTargetMetric('response_time')).toBe('avg_response_time')
    expect(normalizeTargetMetric('waiting_time')).toBe('avg_waiting_time')
  })
  it('classifies metric direction', () => {
    expect(isHigherBetterMetric('throughput')).toBe(true)
    expect(isLowerBetterMetric('avg_waiting_time')).toBe(true)
    expect(isHigherBetterMetric('avg_waiting_time')).toBe(false)
  })
})

describe('guard / recommendation resolution', () => {
  it('prefers the guard algorithm', () => {
    expect(getGuardAlgorithm({ scheduling_algorithm: 'mlfq' })).toBe('MLFQ')
  })
  it('falls back to the recommendation, then the default', () => {
    expect(getGuardAlgorithm(null, { recommended_scheduling_algorithm: 'sjf' })).toBe('SJF')
    expect(getGuardAlgorithm(null, null, 'RR')).toBe('RR')
  })
  it('uses the guard fallback algorithm when flagged', () => {
    expect(getGuardAlgorithm({ fallback_used: true, fallback_algorithm: 'rr' })).toBe('RR')
  })
  it('reads recommendation directly', () => {
    expect(getRecommendedAlgorithm({ algorithm: 'fcfs' })).toBe('FCFS')
  })
})

describe('computeAlgorithmJudgment', () => {
  const target = 'avg_waiting_time' // lower is better
  const all = [{ avg_waiting_time: 4 }, { avg_waiting_time: 8 }, { avg_waiting_time: 12 }]

  it('rates the best algorithm SUCCESS', () => {
    expect(computeAlgorithmJudgment({ avg_waiting_time: 4 }, all, target)).toBe('SUCCESS')
  })
  it('rates a clearly-worse algorithm FAIL', () => {
    expect(computeAlgorithmJudgment({ avg_waiting_time: 12 }, all, target)).toBe('FAIL')
  })
  it('forces FAIL on starvation regardless of metric', () => {
    expect(
      computeAlgorithmJudgment({ avg_waiting_time: 4, starvation_occurred: true }, all, target)
    ).toBe('FAIL')
  })
  it('returns UNKNOWN when the metric is missing', () => {
    expect(computeAlgorithmJudgment({}, all, target)).toBe('UNKNOWN')
  })
})

describe('computeBestPerMetric', () => {
  it('picks the min for lower-better and max for higher-better, skipping starvers', () => {
    const comparison = {
      RR:   { avg_waiting_time: 9, throughput: 0.5 },
      MLFQ: { avg_waiting_time: 5, throughput: 0.7 },
      // a starving candidate must never be chosen as best
      SJF:  { avg_waiting_time: 1, throughput: 0.9, starvation_occurred: true },
    }
    const best = computeBestPerMetric(comparison)
    expect(best.avg_waiting_time.algo).toBe('MLFQ')
    expect(best.throughput.algo).toBe('MLFQ')
    expect(best.throughput.higher_better).toBe(true)
  })
  it('returns {} for invalid input', () => {
    expect(computeBestPerMetric(null)).toEqual({})
  })
})

describe('getBackend', () => {
  it('maps xv6-log mode/backend to xv6', () => {
    expect(getBackend({ backend: 'xv6-log' })).toBe('xv6')
    expect(getBackend({ mode: 'xv6' })).toBe('xv6')
  })
  it('defaults to unknown (the simulator backend was removed)', () => {
    expect(getBackend({})).toBe('unknown')
    expect(getBackend(null)).toBe('unknown')
    // legacy data explicitly claiming the removed simulator is still reported
    expect(getBackend({ mode: 'simulator' })).toBe('simulator')
  })
})
