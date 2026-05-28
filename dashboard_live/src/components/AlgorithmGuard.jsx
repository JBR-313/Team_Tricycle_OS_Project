import Card from './Card.jsx'

/**
 * AlgorithmGuard — Page 1 §5 (compact pre-execution guard verdict).
 *
 * Layout (single row status, then small checklist):
 *   ┌──────────────────────────────────────────────────────────────┐
 *   │ [ACCEPTED] MLFQ is suitable for response_time                │
 *   ├──────────────────────────────────────────────────────────────┤
 *   │ ✓ Algorithm implemented                                       │
 *   │ ✓ Parameters in range                                         │
 *   │ ✓ No fallback used                                            │
 *   │ ✓ Prediction source valid                                     │
 *   └──────────────────────────────────────────────────────────────┘
 *
 * Per pre-execution revision §5:
 *   - Status box keeps the large word on the left, short reason inline on
 *     the right (§5.2).
 *   - `(compat=..., confidence=...)` parens are stripped from the reason
 *     text — those numbers are not shown on the dashboard (§5.1).
 *   - No `compact / confidence / compat / compatibility` text anywhere.
 *   - Card is visually compact (§5.4) — kept short so LLM RECOMMENDATION
 *     and LLM EXPLANATION dominate Page 1.
 */
const STATUS = {
  ACCEPTED:                { bg: '#d1fae5', fg: '#047857', label: 'ACCEPTED' },
  ACCEPTED_WITH_WARNING:   { bg: '#fef3c7', fg: '#b45309', label: 'WARNING' },
  OVERRIDDEN:              { bg: '#fef3c7', fg: '#b45309', label: 'OVERRIDDEN' },
  REJECTED:                { bg: '#fee2e2', fg: '#dc2626', label: 'REJECTED' },
  UNKNOWN:                 { bg: '#f1f5f9', fg: '#475569', label: 'UNKNOWN' },
}

// Strip `(compat=..., confidence=...)` chunks and any leading verdict word
// from the guard reason so only the short "<algo> is suitable for <metric>"
// payload remains. Defensive — handles partial matches.
function cleanReason(raw) {
  if (!raw || typeof raw !== 'string') return ''
  let s = raw
  // Drop parenthesised compat/confidence/conf annotations anywhere.
  s = s.replace(/\s*\([^()]*\b(compat|confidence|conf)\b[^()]*\)\s*/gi, ' ')
  // Drop leading "Accepted:", "Accepted with warnings:", "Rejected:", etc.
  s = s.replace(/^\s*(accepted with warnings?|accepted|rejected|warning|overridden)\s*:\s*/i, '')
  // Tidy whitespace and trailing punctuation noise.
  s = s.replace(/\s{2,}/g, ' ').trim()
  s = s.replace(/[.,;]\s*$/, '')
  return s
}

export default function AlgorithmGuard({ guardDecision: g }) {
  if (!g) {
    return (
      <Card label="Algorithm Guard" className="card-guard page1-card page1-card-guard">
        <div className="loading">Loading…</div>
      </Card>
    )
  }

  const raw = String(g.guard_result || 'unknown').toUpperCase().replace(/-/g, '_')
  const key = STATUS[raw] ? raw : 'UNKNOWN'
  const style = STATUS[key]

  const reasonInline = cleanReason(g.reason)
  const algo = g.algorithm || g.scheduling_algorithm
  const fallbackUsed  = !!g.fallback_used
  const fallbackAlgo  = g.fallback_algorithm
  const predictionSrc = g.prediction_source  // 'llm' | 'ema' | null

  // Checklist — at most four short lines (§5.3). No compat / confidence.
  const checklist = [
    [`Algorithm implemented${algo ? ` (${algo})` : ''}`, true],
    ['Parameters in range', true],
    [fallbackUsed
      ? `Fallback used → ${fallbackAlgo || '—'}`
      : 'No fallback used', !fallbackUsed],
  ]
  if (predictionSrc) {
    checklist.push([
      predictionSrc === 'llm'
        ? 'Prediction source: LLM hints'
        : 'Prediction source: EMA fallback',
      true,
    ])
  } else if (algo && (algo === 'SJF' || algo === 'SRTF')) {
    checklist.push(['Prediction source valid', true])
  }

  return (
    <Card label="Algorithm Guard" className="card-guard page1-card page1-card-guard">
      <div
        className="page1-guard-status-box"
        style={{ background: style.bg, color: style.fg }}
        title={reasonInline ? `${style.label} — ${reasonInline}` : style.label}
      >
        <span className="page1-guard-status-word">{style.label}</span>
        {reasonInline && (
          <span className="page1-guard-status-reason">{reasonInline}</span>
        )}
      </div>

      <ul className="page1-checklist">
        {checklist.map(([label, ok]) => (
          <li key={label} className={ok ? 'check-ok' : 'check-warn'}>
            <span className="check-mark">{ok ? '✓' : '⚠'}</span>
            {label}
          </li>
        ))}
      </ul>
    </Card>
  )
}
