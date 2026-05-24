import Card from './Card.jsx'
import { recommendation as rec } from '../data/demoData.js'

export default function LLMRecommendation() {
  const algo   = rec.recommended_scheduling_algorithm
  const target = rec.target_metric?.replace(/_/g, ' ')
  const risks  = rec.risks || []
  const params = rec.params || {}
  const reason = rec.reason || ''

  const paramStr = Object.entries(params)
    .map(([k, v]) => `${k}=${Array.isArray(v) ? v.join('/') : v}`)
    .join('  ')

  return (
    <Card label="LLM Recommendation" className="card-rec">
      <div style={{ marginBottom: 4, flexShrink: 0 }}>
        <span className="pill" style={{ background: '#ede9fe', color: '#6d28d9' }}>{algo}</span>
        <span className="pill" style={{ background: '#dbeafe', color: '#1d4ed8' }}>↳ {target}</span>
        {risks.map(r => (
          <span key={r} className="pill" style={{ background: '#fef3c7', color: '#b45309', fontSize: '0.57rem' }}>
            {r.replace(/_/g, ' ')}
          </span>
        ))}
      </div>
      {paramStr && (
        <div style={{ fontSize: '0.50rem', color: '#b0b8cc', marginBottom: 4, flexShrink: 0, fontFamily: 'monospace', letterSpacing: '0.02em' }}>
          {paramStr}
        </div>
      )}
      {reason && (
        <div style={{
          fontSize: '0.63rem',
          color: '#334155',
          lineHeight: 1.55,
          overflow: 'hidden',
          display: '-webkit-box',
          WebkitLineClamp: 3,
          WebkitBoxOrient: 'vertical',
          flexShrink: 0,
        }}>
          {reason}
        </div>
      )}
    </Card>
  )
}
