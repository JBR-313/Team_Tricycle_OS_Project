import Card from './Card.jsx'
import { ALGO_COLORS } from '../data/demoData.js'
import { computeAlgorithmJudgment, normalizeAlgo, normalizeTargetMetric } from '../data/schemaCompat.js'

const COLS = [
  { key: 'avg_response_time',   label: 'Avg RT',  lowerBetter: true  },
  { key: 'avg_waiting_time',    label: 'Avg WT',  lowerBetter: true  },
  { key: 'avg_turnaround_time', label: 'Avg TAT', lowerBetter: true  },
  { key: 'throughput',          label: 'Thru',    lowerBetter: false },
  { key: 'preemption_count',    label: 'Pre',     lowerBetter: true  },
  { key: 'starvation_occurred', label: 'Starv',   lowerBetter: null  },
  { key: 'judgment',            label: 'Judge',   lowerBetter: null  },
]

function fmt(v, key) {
  if (v === null || v === undefined) return '—'
  if (key === 'starvation_occurred') return v ? 'Yes' : 'No'
  if (typeof v === 'number') return key === 'throughput' ? v.toFixed(3) : v.toFixed(2)
  return String(v)
}

export default function AlgorithmComparison({ metrics, recommendation, selectedMetric }) {
  const cmp     = (metrics || {}).comparison || {}
  const rec     = recommendation || {}
  const recAlgo = normalizeAlgo(rec.recommended_scheduling_algorithm || rec.algorithm)
  // JUDGE + column highlight follow the SELECTED metric (dropdown), not the
  // recommendation's target_metric or any stale stored judgment.
  const sel     = normalizeTargetMetric(selectedMetric || rec.target_metric || 'avg_response_time')
  const tgtCol  = COLS.find(c => c.key === sel)?.label

  const rows = Object.entries(cmp)
  const allCmp = Object.values(cmp)

  // Pre-compute best/worst per numeric column
  const colStats = {}
  for (const col of COLS) {
    if (col.lowerBetter === null) continue
    const vals = rows.map(([, v]) => v[col.key]).filter(v => typeof v === 'number')
    if (!vals.length) continue
    colStats[col.key] = {
      best:  col.lowerBetter ? Math.min(...vals) : Math.max(...vals),
      worst: col.lowerBetter ? Math.max(...vals) : Math.min(...vals),
    }
  }

  return (
    <Card label="Algorithm Comparison" className="card-cmp">
      <div className="inner-scroll">
        <table className="cmp-table">
          <thead>
            <tr>
              <th>Algo</th>
              {COLS.map(c => (
                <th key={c.key} className={c.label === tgtCol ? 'col-highlight' : ''}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([algo, vals]) => {
              const isRec = algo === recAlgo
              return (
                <tr key={algo} className={isRec ? 'recommended' : ''}>
                  <td style={{
                    fontWeight: isRec ? 700 : 400,
                    color: isRec ? '#7c3aed' : '#334155',
                  }}>
                    <span style={{
                      display: 'inline-block',
                      width: 6, height: 6, borderRadius: '50%',
                      background: ALGO_COLORS[algo] || '#94a3b8',
                      marginRight: 4, verticalAlign: 'middle',
                    }} />
                    {algo}
                  </td>
                  {COLS.map(c => {
                    const raw = vals[c.key]
                    let v   = fmt(raw, c.key)
                    let style = {}

                    if (c.key === 'judgment') {
                      // Metric-aware: recompute for the selected metric (starvation ⇒ FAIL).
                      v = computeAlgorithmJudgment(vals, allCmp, sel)
                      style = {
                        color: { SUCCESS: '#059669', 'NEAR-SUCCESS': '#1d4ed8', FAIL: '#dc2626', UNKNOWN: '#64748b' }[v] || '#334155',
                        fontWeight: 700,
                      }
                    } else if (c.key === 'starvation_occurred') {
                      style = { color: v === 'Yes' ? '#dc2626' : '#059669' }
                    } else if (colStats[c.key] && typeof raw === 'number') {
                      const { best, worst } = colStats[c.key]
                      if (raw === best)  style = { background: 'rgba(16,185,129,0.13)', color: '#059669', fontWeight: 700 }
                      else if (raw === worst) style = { background: 'rgba(244,63,94,0.10)', color: '#dc2626' }
                    }

                    return (
                      <td
                        key={c.key}
                        className={c.label === tgtCol ? 'col-highlight' : ''}
                        style={style}
                      >
                        {v}
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
