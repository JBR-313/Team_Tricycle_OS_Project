import Card from './Card.jsx'
import { recommendation as rec, metrics, ALGO_COLORS } from '../data/demoData.js'

const PARAM_LABELS = {
  queues: 'Queues',
  quantum: 'Quantum',
  aging_threshold: 'Aging Threshold',
  boost_interval: 'Boost Interval',
  alpha: 'Alpha (α)',
  initial_burst: 'Initial Burst',
  time_slice: 'Time Slice',
}

const JUDGE_COLOR = {
  SUCCESS: '#15803d',
  'NEAR-SUCCESS': '#b45309',
  FAIL: '#b91c1c',
}

const fmtVal = (v) => (Array.isArray(v) ? v.join(' / ') : String(v))
const labelOf = (k) => PARAM_LABELS[k] || k.replace(/_/g, ' ')

export default function LLMRecommendation() {
  const algo      = rec.recommended_scheduling_algorithm
  const target    = rec.target_metric?.replace(/_/g, ' ')
  const risks     = rec.risks || []
  const params    = rec.params || {}
  const reason    = rec.reason || ''
  const interp    = rec.workload_interpretation || {}
  const wlType    = interp.workload_type?.replace(/_/g, ' ')
  const mainRisks = interp.main_risks || []
  const model     = rec.llm_model
  const paramEntries = Object.entries(params)

  // Rank every candidate by the target metric (time metrics: lower is better)
  const metricKey = rec.target_metric
  const comparison = metrics.comparison || {}
  const alternatives = Object.entries(comparison)
    .map(([name, m]) => ({ name, value: m[metricKey], judgment: m.judgment }))
    .filter(r => typeof r.value === 'number')
    .sort((a, b) => a.value - b.value)
  const maxVal = Math.max(...alternatives.map(r => r.value), 1)

  return (
    <Card label="LLM Recommendation" className="card-rec">
      {/* Hero — the headline decision */}
      <div className="rec-hero">
        <div className="rec-hero-algo">{algo}</div>
        <div className="rec-hero-meta">
          <span className="rec-hero-target">↳ optimizing <strong>{target}</strong></span>
          {model && <span className="rec-hero-model">{model}</span>}
        </div>
      </div>

      <hr className="divider" />

      {/* Parameters */}
      {paramEntries.length > 0 && (
        <div className="rec-section">
          <div className="rec-section-label">Parameters</div>
          <div className="rec-param-grid">
            {paramEntries.map(([k, v]) => (
              <div key={k} className="rec-param">
                <div className="rec-param-key">{labelOf(k)}</div>
                <div className="rec-param-val">{fmtVal(v)}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Reasoning */}
      {reason && (
        <div className="rec-section">
          <div className="rec-section-label">Reasoning</div>
          <div className="rec-reason">{reason}</div>
        </div>
      )}

      {/* Considered alternatives — ranked by the target metric */}
      {alternatives.length > 0 && (
        <div className="rec-section rec-alt-section">
          <div className="rec-section-label">
            Considered Alternatives · ranked by {target}
          </div>
          <div className="rec-alt-list">
            {alternatives.map(({ name, value, judgment }) => {
              const isRec = name.toLowerCase() === algo.toLowerCase()
              return (
                <div key={name} className={`rec-alt-row ${isRec ? 'is-rec' : ''}`}>
                  <span className="rec-alt-name">
                    {isRec && <span className="rec-alt-star">★</span>}
                    {name}
                  </span>
                  <span className="rec-alt-bar-track">
                    <span
                      className="rec-alt-bar-fill"
                      style={{
                        width: `${Math.max((value / maxVal) * 100, 3)}%`,
                        background: isRec ? (ALGO_COLORS[name] || 'var(--accent)') : 'rgba(100,116,139,0.32)',
                      }}
                    />
                  </span>
                  <span className="rec-alt-val">{value}</span>
                  {judgment && (
                    <span className="rec-alt-judge" style={{ color: JUDGE_COLOR[judgment] || 'var(--text-3)' }}>
                      {judgment === 'NEAR-SUCCESS' ? 'NEAR' : judgment}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Workload interpretation + risk flags handed to the Guard */}
      <div className="rec-foot">
        {wlType && (
          <span className="pill" style={{ background: '#e0f2fe', color: '#0369a1' }}>{wlType}</span>
        )}
        {mainRisks.map(r => (
          <span key={r} className="pill" style={{ background: '#fef3c7', color: '#b45309', fontSize: '0.57rem' }}>
            ⚠ {r.replace(/_/g, ' ')}
          </span>
        ))}
        {risks.map(r => (
          <span key={r} className="pill" style={{ background: '#fee2e2', color: '#b91c1c', fontSize: '0.57rem' }}>
            risk: {r.replace(/_/g, ' ')}
          </span>
        ))}
      </div>
    </Card>
  )
}
