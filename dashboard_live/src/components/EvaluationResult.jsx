import Card from './Card.jsx'
import { isHigherBetterMetric, normalizeTargetMetric } from '../data/schemaCompat.js'

export default function EvaluationResult({ metrics, recommendation: rec }) {
  if (!metrics || !rec) return <Card label="Evaluation Result" className="card-eval"><div className="loading">Loading…</div></Card>

  const jdg    = metrics.judgment || '—'
  const regret = metrics.regret_score
  const starv  = metrics.starvation_occurred

  // Presentation-safe regret formatting. When `best_metric` is tiny, regret can
  // exceed 1000% and the raw float ("regret 10.83" = 1083%) is misleading on a
  // demo screen. We display percentages, capping the visible range at >999%.
  // The internal `regret_score` is left untouched for downstream consumers.
  function formatRegretLabel(r) {
    if (r == null) return null
    const pct = r * 100
    if (pct >= 999.5) return '>999% (best≈0, see explanation)'
    if (pct < 1) return `${pct.toFixed(2)}%`
    return `${pct.toFixed(1)}%`
  }
  const regretLabel = formatRegretLabel(regret)
  const cmp    = metrics.comparison || {}
  const recAlgo = rec.recommended_scheduling_algorithm || rec.algorithm
  const tgt     = normalizeTargetMetric(rec.target_metric || 'avg_response_time')
  const higher  = isHigherBetterMetric(tgt)

  // Direction-aware best: max for throughput, min for the lower-is-better metrics.
  let bestAlgo = '—', bestVal = higher ? -Infinity : Infinity
  for (const [a, v] of Object.entries(cmp)) {
    const val = v[tgt]
    if (typeof val === 'number' && (higher ? val > bestVal : val < bestVal)) {
      bestVal = val; bestAlgo = a
    }
  }

  const jBg = { SUCCESS: '#d1fae5', 'NEAR-SUCCESS': '#dbeafe', FAIL: '#fee2e2' }[jdg] || '#f1f5f9'
  const jFg = { SUCCESS: '#059669', 'NEAR-SUCCESS': '#1d4ed8', FAIL: '#dc2626' }[jdg] || '#64748b'
  const recVal = cmp[recAlgo]?.[tgt]

  return (
    <Card label="Evaluation Result" className="card-eval">
      <div style={{ flexShrink: 0, marginBottom: 4 }}>
        <span className="pill" style={{ background: jBg, color: jFg, fontSize: '0.72rem' }}>{jdg}</span>
        {regretLabel && (
          <span className="pill" style={{ background: '#f1f5f9', color: '#64748b' }}
                title={`raw regret_score = ${regret}`}>regret {regretLabel}</span>
        )}
        <span className="pill" style={{
          background: starv ? '#fee2e2' : '#d1fae5',
          color: starv ? '#dc2626' : '#059669',
        }}>
          {starv ? 'Starvation!' : 'No Starvation'}
        </span>
      </div>
      <hr className="divider" />
      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '3px 10px', fontSize: '0.60rem' }}>
          {(() => {
            const lowerBetter = !higher
            let delta = null, deltaColor = '#64748b', deltaArrow = ''
            if (recVal != null && Number.isFinite(bestVal)) {
              delta = recVal - bestVal
              const worse = lowerBetter ? delta > 0 : delta < 0
              deltaColor = worse ? '#dc2626' : '#059669'
              deltaArrow = worse ? '▲' : (Math.abs(delta) < 0.001 ? '=' : '▼')
            }
            const rows = [
              ['Target',       tgt.replace(/_/g, ' '), '#334155'],
              ['Best Algo',    bestAlgo,                '#059669'],
              ['LLM Selected', recAlgo,                 '#7c3aed'],
              ['Δ vs Best',    delta != null
                ? <span style={{ color: deltaColor, fontWeight: 700 }}>{deltaArrow} {Math.abs(delta).toFixed(2)}</span>
                : '—', '#334155'],
            ]
            return rows
          })().map(([k, v, c]) => (
            <div key={k}>
              <div style={{ fontSize: '0.50rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{k}</div>
              <div style={{ fontWeight: 700, color: c, marginTop: 1 }}>{v}</div>
            </div>
          ))}
        </div>
        {cmp[recAlgo] && (
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', paddingTop: 6 }}>
            {[
              { k: 'avg_response_time',   label: 'RT' },
              { k: 'avg_waiting_time',    label: 'WT' },
              { k: 'avg_turnaround_time', label: 'TAT' },
              { k: 'throughput',          label: 'THRU' },
            ].map(({ k, label }) => {
              const v = cmp[recAlgo][k]
              return typeof v === 'number' ? (
                <span key={k} style={{
                  fontSize: '0.52rem', color: '#64748b',
                  background: 'rgba(237,233,254,0.55)',
                  borderRadius: 5, padding: '2px 6px',
                }}>
                  {label} <strong style={{ color: '#7c3aed' }}>
                    {k === 'throughput' ? v.toFixed(3) : v.toFixed(2)}
                  </strong>
                </span>
              ) : null
            })}
          </div>
        )}
      </div>
    </Card>
  )
}
