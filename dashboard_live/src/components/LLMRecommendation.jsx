import Card from './Card.jsx'
import Typewriter from './Typewriter.jsx'

/**
 * LLMRecommendation — Page 1 §2 (pre-execution).
 *
 * Layout:
 *   ┌ algorithm name (big)                          parameters (small) ┐
 *   ├─────────────────────────────────────────────────────────────────┤
 *   │ Up to 4 short paragraphs of pre-execution reasoning             │
 *   └─────────────────────────────────────────────────────────────────┘
 *
 * Per pre-execution revision:
 *   - NO target-metric pill next to the algorithm name (§2.1).
 *   - Parameters live on the right side of the header row (§2.2).
 *   - Reason is split into at most 4 short paragraphs (§2.4).
 *   - No post-execution evidence anywhere here (§0).
 */
function splitReason(reason) {
  if (!reason || typeof reason !== 'string') return []
  return reason
    .split(/(?<=[.!?])\s+/)
    .map(s => s.trim())
    .filter(Boolean)
    .slice(0, 4)
}

function formatParams(params) {
  if (!params || typeof params !== 'object') return ''
  return Object.entries(params)
    .map(([k, v]) => `${k}=${Array.isArray(v) ? v.join('/') : v}`)
    .join(' · ')
}

export default function LLMRecommendation({ recommendation: rec, show = true, typing = false }) {
  // Pre-reveal placeholder: the LLM is still "thinking". Content is withheld
  // until the reveal sequence reaches this card so the demo does not look
  // pre-generated.
  if (!show) {
    return (
      <Card label="LLM Recommendation" className="card-rec page1-card page1-card-rec">
        <div className="llm-placeholder">
          <span className="llm-placeholder-dots"><i /><i /><i /></span>
          <span className="llm-placeholder-text">Selecting a scheduling algorithm…</span>
        </div>
      </Card>
    )
  }

  if (!rec) {
    return (
      <Card label="LLM Recommendation" className="card-rec page1-card page1-card-rec">
        <div className="loading">Loading…</div>
      </Card>
    )
  }

  const algo = rec.recommended_scheduling_algorithm || rec.algorithm || '—'
  const paragraphs = splitReason(rec.reason)
  const paramStr = formatParams(rec.params)
  // When typing, animate the reason as one continuous typewriter block;
  // otherwise render the pre-split paragraphs statically.
  const reasonText = paragraphs.join(' ')

  return (
    <Card label="LLM Recommendation" className="card-rec page1-card page1-card-rec">
      <div className="page1-rec-header">
        <div className="page1-algo">{algo}</div>
        {paramStr && (
          <div className="page1-params" title="Parameters proposed by the LLM">
            {paramStr}
          </div>
        )}
      </div>

      {paragraphs.length > 0 ? (
        typing ? (
          <div className="page1-reason">
            <p className="page1-reason-line">
              <Typewriter text={reasonText} start speed={14} />
            </p>
          </div>
        ) : (
          <div className="page1-reason">
            {paragraphs.map((p, i) => (
              <p key={i} className="page1-reason-line">{p}</p>
            ))}
          </div>
        )
      ) : (
        <p className="page1-body page1-muted">No recommendation reason provided.</p>
      )}
    </Card>
  )
}
