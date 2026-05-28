import Card from './Card.jsx'
import {
  computeAlgorithmJudgment, normalizeAlgo,
  normalizeTargetMetric, getRecommendedAlgorithm,
} from '../data/schemaCompat.js'

const COLS = [
  { key: 'avg_response_time',   label: 'Avg Response',   short: 'avg_response_time',   lowerBetter: true  },
  { key: 'avg_waiting_time',    label: 'Avg Waiting',    short: 'avg_waiting_time',    lowerBetter: true  },
  { key: 'avg_turnaround_time', label: 'Avg Turnaround', short: 'avg_turnaround_time', lowerBetter: true  },
  { key: 'throughput',          label: 'Throughput',     short: 'throughput',          lowerBetter: false },
  { key: 'preemption_count',    label: 'Preemptions',    short: 'preemption_count',    lowerBetter: true  },
  { key: 'starvation_occurred', label: 'Starvation',     short: 'starvation',          lowerBetter: null  },
  { key: 'judgment',            label: 'Verdict',        short: 'verdict',             lowerBetter: null  },
]

function fmt(v, key) {
  if (v === null || v === undefined) return '—'
  if (key === 'starvation_occurred') return v ? 'Yes' : 'No'
  if (typeof v === 'number') return key === 'throughput' ? v.toFixed(3) : v.toFixed(2)
  return String(v)
}

export default function AlgorithmComparison({ metrics, recommendation: rec, selectedMetric }) {
  if (!metrics || !rec) return <Card label="Algorithm Comparison" className="card-cmp"><div className="loading">Loading…</div></Card>

  const cmp     = metrics.comparison || {}
  const recAlgo = getRecommendedAlgorithm(rec)
  const tgt     = normalizeTargetMetric(selectedMetric || rec.target_metric || 'avg_response_time')
  const tgtCol  = COLS.find(c => c.key === tgt)?.label
  const rows    = Object.entries(cmp)
  const allComparisonMetrics = Object.values(cmp)

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
              <th>Algorithm</th>
              {COLS.map(c => (
                <th
                  key={c.key}
                  className={c.label === tgtCol ? 'col-highlight' : ''}
                  title={c.short}
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([algo, vals]) => {
              const a = normalizeAlgo(algo)
              const isRec = a === recAlgo
              return (
                <tr key={algo} className={isRec ? 'recommended' : ''}>
                  <td className={isRec ? 'cmp-algo-name cmp-algo-rec' : 'cmp-algo-name'}>
                    {a}
                  </td>
                  {COLS.map(c => {
                    const raw = vals[c.key]
                    let v   = fmt(raw, c.key)
                    let style = {}
                    let cellClass = c.label === tgtCol ? 'col-highlight' : ''
                    if (c.key === 'judgment') {
                      v = computeAlgorithmJudgment(vals, allComparisonMetrics, tgt)
                      cellClass += ` cmp-verdict cmp-verdict-${v.toLowerCase().replace('-', '')}`
                    } else if (c.key === 'starvation_occurred') {
                      cellClass += ` cmp-starv-${v.toLowerCase()}`
                    } else if (colStats[c.key] && typeof raw === 'number') {
                      const { best, worst } = colStats[c.key]
                      if (raw === best)       cellClass += ' cmp-cell-best'
                      else if (raw === worst) cellClass += ' cmp-cell-worst'
                    }
                    return (
                      <td key={c.key} className={cellClass.trim()} style={style}>{v}</td>
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
