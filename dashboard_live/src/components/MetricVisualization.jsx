import Card from './Card.jsx'
import { ALGO_COLORS } from './constants.js'
import { normalizeTargetMetric, getRecommendedAlgorithm, normalizeAlgo } from '../data/schemaCompat.js'

const METRICS = [
  { key: 'avg_response_time',   label: 'Avg Response Time' },
  { key: 'avg_waiting_time',    label: 'Avg Waiting Time' },
  { key: 'avg_turnaround_time', label: 'Avg Turnaround Time' },
  { key: 'throughput',          label: 'Throughput' },
  { key: 'max_waiting_time',    label: 'Max Waiting Time' },
  { key: 'preemption_count',    label: 'Preemption Count' },
]

// Optimisation direction per metric. Lower-is-better for timing metrics,
// higher-is-better for throughput. Used to pick the LED winner — never
// use Math.max() blindly, that would highlight the worst on timing
// metrics.
const METRIC_DIRECTION = {
  avg_response_time:   'min',
  avg_waiting_time:    'min',
  avg_turnaround_time: 'min',
  max_waiting_time:    'min',
  preemption_count:    'min',
  throughput:          'max',
}

function getBestAlgorithms(entries, direction) {
  const valid = entries.filter(e => Number.isFinite(e.val))
  if (valid.length === 0) return []
  const vals = valid.map(e => e.val)
  const best = direction === 'max' ? Math.max(...vals) : Math.min(...vals)
  // Tie handling — return every algorithm that hits the best value.
  return valid
    .filter(e => e.val === best)
    .map(e => normalizeAlgo(e.algo))
}

export default function MetricVisualization({ metrics, recommendation: rec, selectedMetric, onSelectedMetricChange }) {
  if (!metrics || !rec) {
    return (
      <Card label="Metric Visualization" className="card-metric">
        <div className="loading">Loading…</div>
      </Card>
    )
  }

  const cmp     = metrics.comparison || {}
  const recAlgo = getRecommendedAlgorithm(rec)
  const selKey  = normalizeTargetMetric(selectedMetric)
  const direction = METRIC_DIRECTION[selKey] || 'min'

  const entries = Object.entries(cmp)
    .map(([algo, v]) => ({ algo, val: v[selKey] }))
    .filter(e => typeof e.val === 'number')

  // Scale the chart so the tallest visible bar reaches ~74% of the
  // plotting area (paddedMax = maxAbs * 1.35). maxAbs handles current
  // fixture cases where some raw metric values are negative — we still
  // want comparable visual heights without altering the displayed number.
  const maxAbs    = Math.max(...entries.map(e => Math.abs(e.val)), 0.001)
  const paddedMax = maxAbs * 1.35

  const bestSet  = new Set(getBestAlgorithms(entries, direction))
  const hasBest  = bestSet.size > 0
  const selectedLabel = METRICS.find(m => m.key === selKey)?.label || selKey
  const bestText = hasBest ? [...bestSet].join(', ') : '—'

  return (
    <Card label="Metric Visualization" className="card-metric">
      <div className="metric-chart">
        <div className="metric-controls">
          <label htmlFor="metric-select" className="metric-select-label">Metric</label>
          <select
            id="metric-select"
            className="metric-select"
            value={selKey}
            onChange={e => onSelectedMetricChange(e.target.value)}
          >
            {METRICS.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
          </select>
          <span className="metric-best-label">
            Best for <strong>{selectedLabel}</strong>:{' '}
            <strong className="metric-best-name">{bestText}</strong>
          </span>
        </div>
        <div className="metric-bars-wrap">
          <div className="metric-axis-mid" />
          <div className="metric-bars">
            {entries.map(({ algo, val }) => {
              const a     = normalizeAlgo(algo)
              const pct   = (Math.abs(val) / paddedMax) * 100
              const isRec = a === recAlgo
              const isBest = bestSet.has(a)
              const isDim  = hasBest && !isBest
              const barCls = [
                'metric-bar-fill',
                isRec  && 'recommended',
                isBest && 'metric-bar-winner',
                isDim  && 'metric-bar-dimmed',
              ].filter(Boolean).join(' ')
              const barColor = ALGO_COLORS[a] || ALGO_COLORS[algo] || '#94a3b8'
              return (
                <div key={algo} className="metric-bar-col">
                  {isRec && <span className="metric-star">★</span>}
                  <span className="metric-bar-val">{val.toFixed(2)}</span>
                  <div className="metric-bar-track">
                    <div
                      className={barCls}
                      style={{
                        height: `${pct}%`,
                        background: barColor,
                        '--bar-glow-color': barColor,
                      }}
                      title={`${a}: ${val}${isBest ? ' (best for ' + selectedLabel + ')' : ''}`}
                    />
                  </div>
                  <span className="metric-bar-label">{a}</span>
                </div>
              )
            })}
          </div>
          <div className="metric-axis-base" />
        </div>
      </div>
    </Card>
  )
}
