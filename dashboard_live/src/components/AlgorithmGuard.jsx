import Card from './Card.jsx'

/**
 * AlgorithmGuard — Page 1 §5 (compact pre-execution guard verdict).
 *
 * Layout (single row status, then 3-item checklist per acceptance):
 *   ┌──────────────────────────────────────────────────────────────┐
 *   │ [ACCEPTED] MLFQ is suitable for response_time                │
 *   ├──────────────────────────────────────────────────────────────┤
 *   │ ✓ Algorithm implemented                                       │
 *   │ ✓ Parameters in range                                         │
 *   │ ✓ No fallback used                                            │
 *   └──────────────────────────────────────────────────────────────┘
 *
 * Rules:
 *   - Status box keeps the large word on the left, short reason inline on
 *     the right.
 *   - `(compat=..., confidence=...)` parens are stripped from the reason
 *     text — those numbers are not shown on the dashboard.
 *   - No `compact / confidence / compat / compatibility / 0.95` text
 *     anywhere.
 *   - Card is visually compact — kept short so LLM RECOMMENDATION
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

export default function AlgorithmGuard({ guardDecision: g, show = true }) {
  if (!show) {
    return (
      <Card label="Algorithm Guard" className="card-guard page1-card page1-card-guard">
        <div className="llm-placeholder llm-placeholder-sm">
          <span className="llm-placeholder-dots"><i /><i /><i /></span>
          <span className="llm-placeholder-text">Awaiting recommendation to validate…</span>
        </div>
      </Card>
    )
  }
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

  // Checklist — three short lines, each DERIVED from guard_decision (no
  // hardcoded green). The first line reflects whether the algorithm the LLM
  // actually recommended is one the kernel implements; an unsupported pick
  // shows a warning rather than a false ✓.
  const SUPPORTED = ['RR', 'FCFS', 'PRIORITY', 'MLFQ', 'SJF', 'SRTF']
  const recAlgo = String(g.original_recommendation || algo || '').toUpperCase()
  const algoImplemented = SUPPORTED.includes(recAlgo)
  const checklist = [
    [algoImplemented
      ? `Algorithm implemented${algo ? ` (${algo})` : ''}`
      : `Recommended algo unsupported${recAlgo ? ` (${recAlgo})` : ''} → fallback`,
      algoImplemented],
    // The guard always validates and normalises params (clamping out-of-range
    // values to safe defaults), so Role C always receives valid params — this
    // line states that guarantee honestly rather than asserting the LLM's raw
    // params happened to be in range.
    ['Parameters validated by guard', true],
    [fallbackUsed
      ? `Fallback used → ${fallbackAlgo || '—'}`
      : 'No fallback used', !fallbackUsed],
  ]
  // Note: prediction_source remains in guard_decision.json for Page 2/3
  // (post-execution) consumers; intentionally not surfaced on Page 1.
  void predictionSrc

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
