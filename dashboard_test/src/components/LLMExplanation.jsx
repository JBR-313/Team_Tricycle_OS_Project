import Card from './Card.jsx'
import { traceExplanation as ex } from '../data/demoData.js'

const clamp = (n) => ({
  overflow: 'hidden',
  display: '-webkit-box',
  WebkitLineClamp: n,
  WebkitBoxOrient: 'vertical',
})

// Full version (used on Recommend screen)
function FullExplanation() {
  const corrections = ex.runtime_corrections_applied || 0

  return (
    <Card label="LLM Explanation" className="card-expl">
      <div style={{ flexShrink: 0, marginBottom: 6 }}>
        <span className="pill" style={{ background: '#ede9fe', color: '#6d28d9' }}>
          {ex.detected_pattern?.replace(/_/g, ' ')}
        </span>
        {corrections > 0 && (
          <span className="pill" style={{ background: '#fef3c7', color: '#b45309' }}>
            ⚡ {corrections} correction(s)
          </span>
        )}
      </div>

      <div className="inner-scroll" style={{ lineHeight: 1.6 }}>
        {ex.summary && (
          <div style={{ marginBottom: 8, color: 'var(--text-1)', fontWeight: 500, ...clamp(2) }}>
            {ex.summary}
          </div>
        )}

        {ex.main_reason && (
          <>
            <div style={{ fontSize: '0.60rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 3 }}>
              Why
            </div>
            <div style={{ marginBottom: 8, color: '#475569', ...clamp(2) }}>
              {ex.main_reason}
            </div>
          </>
        )}

        {ex.evidence?.length > 0 && (
          <>
            <div style={{ fontSize: '0.60rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 3 }}>
              Evidence
            </div>
            <ul style={{ paddingLeft: 15, margin: '0 0 8px' }}>
              {ex.evidence.slice(0, 4).map((e, i) => (
                <li key={i} style={{ marginBottom: 3, color: '#475569' }}>{e}</li>
              ))}
            </ul>
          </>
        )}

        {ex.suggestion && (
          <div style={{
            color: '#1d4ed8',
            borderLeft: '2px solid rgba(99,102,241,0.35)',
            paddingLeft: 8,
            ...clamp(2),
          }}>
            {ex.suggestion}
          </div>
        )}
      </div>
    </Card>
  )
}

// Compact version (used on Evaluate screen — correction & insight mode)
function CompactExplanation() {
  const corrections = ex.runtime_corrections_applied || 0
  const evidencePicks = (ex.evidence || []).slice(0, 2)

  return (
    <Card label="Correction & Insight" className="card-expl">
      {/* Summary line */}
      {ex.summary && (
        <div style={{
          fontSize: '0.74rem', fontWeight: 600, color: 'var(--text-1)',
          lineHeight: 1.4, marginBottom: 6, flexShrink: 0,
          ...clamp(2),
        }}>
          {ex.summary}
        </div>
      )}

      <div className="inner-scroll" style={{ lineHeight: 1.55 }}>
        {/* Why bullets (max 2) */}
        {ex.main_reason && (
          <div style={{ marginBottom: 6 }}>
            <div style={{ fontSize: '0.58rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 3 }}>
              Why
            </div>
            <ul style={{ paddingLeft: 13, margin: 0 }}>
              {ex.main_reason.split('. ').filter(Boolean).slice(0, 2).map((s, i) => (
                <li key={i} style={{ color: '#475569', marginBottom: 1, ...clamp(1) }}>
                  {s.replace(/\.$/, '')}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Evidence (max 2) */}
        {evidencePicks.length > 0 && (
          <div style={{ marginBottom: 6 }}>
            <div style={{ fontSize: '0.58rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 3 }}>
              Evidence
            </div>
            <ul style={{ paddingLeft: 13, margin: 0 }}>
              {evidencePicks.map((e, i) => (
                <li key={i} style={{ color: '#475569', marginBottom: 1, ...clamp(1) }}>{e}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Correction */}
        <div style={{
          display: 'flex', alignItems: 'flex-start', gap: 5,
          background: corrections > 0 ? 'rgba(245,158,11,0.08)' : 'rgba(99,102,241,0.06)',
          borderRadius: 7, padding: '5px 9px',
        }}>
          <span style={{ fontSize: '0.70rem', flexShrink: 0 }}>
            {corrections > 0 ? '⚡' : '💡'}
          </span>
          <span style={{ fontSize: '0.68rem', color: corrections > 0 ? '#b45309' : '#1d4ed8', lineHeight: 1.35, ...clamp(1) }}>
            {corrections > 0
              ? `${corrections} correction(s). ${ex.suggestion || ''}`
              : (ex.suggestion || 'No corrections needed.')}
          </span>
        </div>
      </div>
    </Card>
  )
}

export default function LLMExplanation({ compact = false }) {
  return compact ? <CompactExplanation /> : <FullExplanation />
}
