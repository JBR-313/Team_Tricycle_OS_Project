import { useState } from 'react'
import Card from './Card.jsx'
import { metrics, recommendation, ALGO_COLORS } from '../data/demoData.js'

const METRICS = [
  { key: 'avg_response_time',   label: 'Avg Response Time' },
  { key: 'avg_waiting_time',    label: 'Avg Waiting Time' },
  { key: 'avg_turnaround_time', label: 'Avg Turnaround Time' },
  { key: 'throughput',          label: 'Throughput' },
  { key: 'max_waiting_time',    label: 'Max Waiting Time' },
  { key: 'preemption_count',    label: 'Preemption Count' },
]

export default function MetricVisualization() {
  const [selKey, setSelKey] = useState('avg_response_time')
  const cmp     = metrics.comparison || {}
  const recAlgo = recommendation.recommended_scheduling_algorithm

  const entries = Object.entries(cmp)
    .map(([algo, v]) => ({ algo, val: v[selKey] }))
    .filter(e => typeof e.val === 'number')

  const maxVal = Math.max(...entries.map(e => e.val), 0.001)

  return (
    <Card label="Metric Visualization" className="card-metric">
      <div className="metric-chart">
        <select
          className="metric-select"
          value={selKey}
          onChange={e => setSelKey(e.target.value)}
        >
          {METRICS.map(m => (
            <option key={m.key} value={m.key}>{m.label}</option>
          ))}
        </select>

        <div className="metric-bars">
          {entries.map(({ algo, val }) => {
            const pct   = (val / maxVal) * 100
            const isRec = algo === recAlgo
            return (
              <div key={algo} className="metric-bar-col">
                {/* recommended star + value label */}
                {isRec && (
                  <span style={{ fontSize: '0.52rem', color: '#7c3aed', fontWeight: 700, lineHeight: 1, flexShrink: 0 }}>★</span>
                )}
                <span className="metric-bar-val">{val.toFixed(2)}</span>

                {/* track: flex column, bar sits at bottom */}
                <div className="metric-bar-track">
                  <div
                    className={`metric-bar-fill ${isRec ? 'recommended' : ''}`}
                    style={{
                      height: `${pct}%`,
                      background: ALGO_COLORS[algo] || '#94a3b8',
                      opacity: isRec ? 1.0 : 0.82,
                    }}
                    title={`${algo}: ${val}`}
                  />
                </div>

                {/* algo label — stays inside col, no overflow */}
                <span className="metric-bar-label">{algo}</span>
              </div>
            )
          })}
        </div>
      </div>
    </Card>
  )
}
