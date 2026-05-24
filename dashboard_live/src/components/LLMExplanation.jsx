import Card from './Card.jsx'

const clamp = (n) => ({
  overflow: 'hidden',
  display: '-webkit-box',
  WebkitLineClamp: n,
  WebkitBoxOrient: 'vertical',
})

export default function LLMExplanation({ traceExplanation: ex }) {
  if (!ex) return <Card label="LLM Explanation" className="card-expl"><div className="loading">Loading…</div></Card>

  const corrections = ex.runtime_corrections_applied || 0

  return (
    <Card label="LLM Explanation" className="card-expl">
      <div style={{ flexShrink: 0, marginBottom: 5 }}>
        <span className="pill" style={{ background: '#ede9fe', color: '#6d28d9' }}>
          {ex.detected_pattern?.replace(/_/g, ' ')}
        </span>
        {corrections > 0 && (
          <span className="pill" style={{ background: '#fef3c7', color: '#b45309' }}>
            ⚡ {corrections} correction(s)
          </span>
        )}
      </div>
      <div className="inner-scroll" style={{ fontSize: '0.64rem', lineHeight: 1.55 }}>
        {ex.summary && (
          <div style={{ marginBottom: 7, color: '#1e293b', fontWeight: 500, ...clamp(2) }}>
            {ex.summary}
          </div>
        )}
        {ex.main_reason && (
          <>
            <div style={{ fontSize: '0.52rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 2 }}>
              Reason
            </div>
            <div style={{ marginBottom: 7, color: '#475569', ...clamp(2) }}>
              {ex.main_reason}
            </div>
          </>
        )}
        {ex.evidence?.length > 0 && (
          <>
            <div style={{ fontSize: '0.52rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 2 }}>
              Evidence
            </div>
            <ul style={{ paddingLeft: 13, margin: '0 0 7px' }}>
              {ex.evidence.slice(0, 4).map((e, i) => (
                <li key={i} style={{ marginBottom: 2, color: '#475569' }}>{e}</li>
              ))}
            </ul>
          </>
        )}
        {ex.suggestion && (
          <div style={{
            color: '#1d4ed8', fontSize: '0.61rem',
            borderLeft: '2px solid rgba(99,102,241,0.35)',
            paddingLeft: 7,
            ...clamp(2),
          }}>
            {ex.suggestion}
          </div>
        )}
      </div>
    </Card>
  )
}
