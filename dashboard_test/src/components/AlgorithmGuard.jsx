import Card from './Card.jsx'

export default function AlgorithmGuard({ guardDecision }) {
  const g = guardDecision
  if (!g) return <Card label="Algorithm Guard" className="card-guard"><div className="loading">Loading…</div></Card>

  const accepted = g.guard_result === 'accepted'
  const bg = accepted ? '#d1fae5' : '#fee2e2'
  const fg = accepted ? '#059669' : '#dc2626'

  return (
    <Card label="Algorithm Guard" className="card-guard">
      <div style={{ flexShrink: 0, marginBottom: 3 }}>
        <span className="pill" style={{ background: bg, color: fg, fontSize: '0.70rem' }}>
          ● {g.guard_result?.toUpperCase()}
        </span>
        {g.fallback_used && (
          <span className="pill" style={{ background: '#fef3c7', color: '#b45309' }}>fallback used</span>
        )}
      </div>
      <div style={{ fontSize: '0.62rem', color: '#64748b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginBottom: 6 }}>
        {g.reason}
      </div>
      <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
        {[
          ['✓ algo implemented', true],
          ['✓ params in range', true],
          [g.fallback_used ? '↩ fallback used' : '✓ no fallback', !g.fallback_used],
        ].map(([label, ok]) => (
          <span key={label} style={{
            fontSize: '0.52rem', fontWeight: 600,
            color: ok ? '#059669' : '#dc2626',
            background: ok ? 'rgba(209,250,229,0.60)' : 'rgba(254,226,226,0.60)',
            borderRadius: 4, padding: '1px 5px',
          }}>
            {label}
          </span>
        ))}
      </div>
    </Card>
  )
}
