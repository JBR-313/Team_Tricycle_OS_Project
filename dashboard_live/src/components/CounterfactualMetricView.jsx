import Card from './Card.jsx'
import {
  computeBestPerMetric,
  normalizeTargetMetric,
  isHigherBetterMetric,
  getRecommendedAlgorithm,
} from '../data/schemaCompat.js'
import { ALGO_COLORS } from './constants.js'

// "Metric trade-off" — read-only counterfactual view that answers
// "if the goal metric changed, would the winner change?".
// Recomputes best-per-metric on the client from metrics.comparison;
// no new data fetched, no LLM call, no data-contract expansion.

// Metric rows displayed, in order. preemption_count is intentionally
// excluded — FCFS trivially wins it (0 preempts), which is not a
// meaningful quality signal. See docs/algorithm_decision_diversity_audit.md §2.
const ROWS = [
  { key: 'avg_response_time',   label: 'Response time' },
  { key: 'avg_waiting_time',    label: 'Waiting time' },
  { key: 'avg_turnaround_time', label: 'Turnaround time' },
  { key: 'max_waiting_time',    label: 'Max waiting' },
  { key: 'throughput',          label: 'Throughput' },
]

function fmt(value, key) {
  if (typeof value !== 'number') return '—'
  if (key === 'throughput') return value.toFixed(3)
  if (key === 'max_waiting_time' || key === 'preemption_count') {
    return Number.isInteger(value) ? String(value) : value.toFixed(2)
  }
  return value.toFixed(2)
}

function deltaCell(metricKey, bestVal, llmVal, higher) {
  if (typeof bestVal !== 'number' || typeof llmVal !== 'number') return '—'
  const same = Math.abs(bestVal - llmVal) < 1e-9
  if (same) return <span style={{ color: '#059669', fontWeight: 600 }}>= best</span>
  const diff = higher ? bestVal - llmVal : llmVal - bestVal
  // diff > 0 ⇒ LLM is worse than best on this metric.
  const arrow = '▼'
  return (
    <span style={{ color: '#dc2626', fontWeight: 600 }}>
      {arrow} {fmt(Math.abs(diff), metricKey)}
    </span>
  )
}

export default function CounterfactualMetricView({ metrics, recommendation }) {
  const comparison = metrics?.comparison
  if (!comparison || typeof comparison !== 'object' || !Object.keys(comparison).length) {
    return (
      <Card label="Metric trade-off" className="card-cf">
        <div className="loading">Metric trade-off — not available for this snapshot.</div>
      </Card>
    )
  }

  const best = computeBestPerMetric(comparison)
  const llmAlgo = getRecommendedAlgorithm(recommendation, null)
  const llmRow = (llmAlgo && comparison[llmAlgo]) || null
  const target = normalizeTargetMetric(recommendation?.target_metric)

  // Tally how often the LLM-selected algorithm is itself the best.
  const visibleRows = ROWS.filter(r => best[r.key])
  const llmWins = visibleRows.filter(r => best[r.key]?.algo === llmAlgo).length

  return (
    <Card label="Metric trade-off" className="card-cf">
      <div style={{ fontSize: '0.55rem', color: '#94a3b8', marginBottom: 4, flexShrink: 0 }}>
        If the goal metric changed, who would win on this workload?
      </div>
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
        <table style={{ width: '100%', fontSize: '0.58rem', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ color: '#94a3b8', textAlign: 'left' }}>
              <th style={{ padding: '2px 4px', fontWeight: 600 }}>Metric</th>
              <th style={{ padding: '2px 4px', fontWeight: 600 }}>Best</th>
              <th style={{ padding: '2px 4px', fontWeight: 600, textAlign: 'right' }}>Value</th>
              <th style={{ padding: '2px 4px', fontWeight: 600, textAlign: 'right' }}>vs LLM</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map(r => {
              const b = best[r.key]
              if (!b) {
                return (
                  <tr key={r.key} style={{ color: '#94a3b8' }}>
                    <td style={{ padding: '2px 4px' }}>{r.label}</td>
                    <td colSpan={3} style={{ padding: '2px 4px', fontStyle: 'italic' }}>
                      — (no candidates)
                    </td>
                  </tr>
                )
              }
              const isTarget = r.key === target
              const dot = ALGO_COLORS[b.algo] || '#94a3b8'
              const llmVal = llmRow ? llmRow[r.key] : null
              return (
                <tr
                  key={r.key}
                  style={{
                    background: isTarget ? 'rgba(124,58,237,0.07)' : 'transparent',
                    borderLeft: isTarget ? '2px solid #7c3aed' : '2px solid transparent',
                  }}
                >
                  <td style={{ padding: '2px 4px', color: '#334155', fontWeight: isTarget ? 700 : 500 }}>
                    {r.label}
                    {isTarget && (
                      <span className="pill" style={{
                        marginLeft: 4,
                        background: '#ede9fe', color: '#6d28d9',
                        fontSize: '0.48rem',
                      }}>target</span>
                    )}
                  </td>
                  <td style={{ padding: '2px 4px' }}>
                    <span style={{
                      display: 'inline-block', width: 5, height: 5, borderRadius: '50%',
                      background: dot, marginRight: 3, verticalAlign: 'middle',
                    }} />
                    <span style={{ color: '#334155', fontWeight: 600 }}>{b.algo}</span>
                  </td>
                  <td style={{ padding: '2px 4px', textAlign: 'right', color: '#475569', fontFamily: 'monospace' }}>
                    {fmt(b.value, r.key)}
                  </td>
                  <td style={{ padding: '2px 4px', textAlign: 'right' }}>
                    {b.algo === llmAlgo
                      ? <span style={{ color: '#059669', fontWeight: 600 }}>= LLM</span>
                      : deltaCell(r.key, b.value, llmVal, b.higher_better)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div style={{
        fontSize: '0.55rem', color: '#64748b', marginTop: 4, flexShrink: 0,
        borderTop: '1px solid #e2e8f0', paddingTop: 4,
      }}>
        LLM-selected <strong style={{ color: '#7c3aed' }}>{llmAlgo || '—'}</strong> wins{' '}
        <strong style={{ color: llmWins === visibleRows.length ? '#059669' : '#334155' }}>
          {llmWins}/{visibleRows.length}
        </strong>{' '}
        metric goals on this workload.
      </div>
    </Card>
  )
}
