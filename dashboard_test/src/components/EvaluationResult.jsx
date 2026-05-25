import Card from './Card.jsx'
import { metrics, recommendation, PROC_COLORS } from '../data/demoData.js'

export default function EvaluationResult() {
  const jdg    = metrics.judgment || '—'
  const regret = metrics.regret_score
  const starv  = metrics.starvation_occurred
  const cmp    = metrics.comparison || {}
  const perProc = metrics.per_process || []
  const recAlgo = recommendation.recommended_scheduling_algorithm
  const tgt     = recommendation.target_metric || 'avg_response_time'

  // Find best algorithm for target metric
  let bestAlgo = '—', bestVal = Infinity
  for (const [a, v] of Object.entries(cmp)) {
    const val = v[tgt]
    if (typeof val === 'number' && val < bestVal) { bestVal = val; bestAlgo = a }
  }

  const jBg = { SUCCESS: '#d1fae5', 'NEAR-SUCCESS': '#dbeafe', FAIL: '#fee2e2' }[jdg] || '#f1f5f9'
  const jFg = { SUCCESS: '#059669', 'NEAR-SUCCESS': '#1d4ed8', FAIL: '#dc2626' }[jdg] || '#64748b'
  const recVal = cmp[recAlgo]?.[tgt]

  return (
    <Card label="Evaluation Result" className="card-eval">
      <div style={{ flexShrink: 0, marginBottom: 4 }}>
        <span className="pill" style={{ background: jBg, color: jFg, fontSize: '0.72rem' }}>{jdg}</span>
        {regret != null && (
          <span className="pill" style={{ background: '#f1f5f9', color: '#64748b' }}>regret {regret.toFixed(2)}</span>
        )}
        <span className="pill" style={{
          background: starv ? '#fee2e2' : '#d1fae5',
          color: starv ? '#dc2626' : '#059669',
        }}>
          {starv ? 'Starvation!' : 'No Starvation'}
        </span>
      </div>
      <hr className="divider" />
      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{
          flexShrink: 0,
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '3px 10px',
          fontSize: '0.60rem',
        }}>
          {(() => {
            // direction: lower is better for most metrics except throughput
            const lowerBetter = tgt !== 'throughput'
            let delta = null, deltaColor = '#64748b', deltaArrow = ''
            if (recVal != null && bestVal < Infinity) {
              delta = recVal - bestVal
              const worse = lowerBetter ? delta > 0 : delta < 0
              deltaColor = worse ? '#dc2626' : '#059669'
              deltaArrow = worse ? '▲' : (Math.abs(delta) < 0.001 ? '=' : '▼')
            }
            const rows = [
              ['Target',      tgt.replace(/_/g, ' '), '#334155'],
              ['Best Algo',   bestAlgo,                '#059669'],
              ['LLM Selected',recAlgo,                 '#7c3aed'],
              ['Δ vs Best',   delta != null
                ? <span style={{ color: deltaColor, fontWeight: 700 }}>{deltaArrow} {Math.abs(delta).toFixed(2)}</span>
                : '—',                                 '#334155'],
            ]
            return rows
          })().map(([k, v, c]) => (
            <div key={k}>
              <div style={{ fontSize: '0.50rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{k}</div>
              <div style={{ fontWeight: 700, color: c, marginTop: 1 }}>{v}</div>
            </div>
          ))}
        </div>

        {/* Per-process breakdown — fills the middle */}
        {perProc.length > 0 && (
          <div className="eval-proc">
            <div className="eval-proc-head">
              <span>Per-Process · {recAlgo}</span>
            </div>
            <div className="eval-proc-table">
              <div className="eval-proc-row eval-proc-row-head">
                <span>PID</span><span>Arr</span><span>Resp</span><span>Wait</span><span>TAT</span>
              </div>
              {perProc.map(p => (
                <div key={p.pid} className="eval-proc-row">
                  <span className="eval-proc-pid">
                    <span className="eval-proc-dot" style={{ background: PROC_COLORS[p.pid] || '#94a3b8' }} />
                    P{p.pid}
                  </span>
                  <span>{p.arrival_time}</span>
                  <span>{p.response_time}</span>
                  <span>{p.waiting_time}</span>
                  <span>{p.turnaround_time}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {cmp[recAlgo] && (
          <div style={{ flexShrink: 0, display: 'flex', gap: 4, flexWrap: 'wrap', paddingTop: 6 }}>
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
