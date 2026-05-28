import Card from './Card.jsx'

// Preview-only runtime-correction card. Reads three optional artifacts:
//   runtime_events.json
//   correction_proposal.json
//   correction_guard_decision.json
// and surfaces them. Nothing on this card was applied to xv6 — the
// banner says so explicitly and the title carries a "(preview)" tag.
//
// The card hides itself if neither events nor a proposal exist for the
// current live-data root (e.g. the orchestrator ran but the detector
// found no scheduling problems, which is the common path on the
// healthy interactive workload).
//
// See docs/runtime_correction_preview_design.md for the schema and the
// honest framing (no CORRECTION_APPLIED trace event; xv6 is unchanged).

const SEVERITY_COLOR = {
  high:   { dot: '#dc2626', bg: '#fee2e2', fg: '#b91c1c' },
  medium: { dot: '#d97706', bg: '#fef3c7', fg: '#92400e' },
  low:    { dot: '#475569', bg: '#f1f5f9', fg: '#334155' },
}

function paramSummary(params) {
  if (!params || typeof params !== 'object') return null
  const order = ['queues', 'quantum', 'aging_threshold', 'boost_interval',
                 'alpha_percent', 'initial', 'min', 'max']
  const seen = new Set(order)
  const fmt = (k, v) => {
    if (Array.isArray(v)) return `${k}=${v.join('/')}`
    return `${k}=${v}`
  }
  const parts = []
  for (const k of order) {
    if (params[k] !== undefined) parts.push(fmt(k, params[k]))
  }
  for (const k of Object.keys(params)) {
    if (seen.has(k)) continue
    parts.push(fmt(k, params[k]))
  }
  return parts.length ? parts.join('  ') : null
}

export default function RuntimeCorrectionPreview({
  runtimeEvents,
  correctionProposal,
  correctionGuardDecision,
}) {
  const events = runtimeEvents?.events || []
  const proposal = correctionProposal && correctionProposal.preview_only === true
    ? correctionProposal : null
  const decision = correctionGuardDecision && correctionGuardDecision.preview_only === true
    ? correctionGuardDecision : null

  // Hide when no preview pipeline ran at all (runtime_events.json absent).
  // We still hide if events is undefined/null — the orchestrator preview
  // step did not write the file for this snapshot.
  if (!runtimeEvents) return null

  // Healthy run — file exists with 0 events. Render a compact monitor
  // strip so the audience sees the detector is watching, without
  // fabricating events. No proposal / guard sections; preview honesty
  // is preserved.
  if (!events.length && !proposal) {
    return (
      <Card label="Runtime Correction" className="card-cor-preview">
        <div className="cor-preview-banner">
          Preview only — not applied to xv6.
        </div>
        <div className="cor-status-row">
          <span className="cor-status-dot cor-status-ok" />
          <span className="cor-status-text">
            Runtime correction: <strong>Not needed</strong>
          </span>
        </div>
        <p className="cor-status-detail">
          No scheduling issue exceeded the correction threshold for this run.
        </p>
      </Card>
    )
  }

  const accepted = decision?.guard_result === 'accepted'

  return (
    <Card label="Runtime Correction" className="card-cor-preview">
      <div className="cor-preview-banner">
        Preview only — not applied to xv6.
      </div>

      {events.length > 0 && (
        <div style={{ marginBottom: 4, flexShrink: 0 }}>
          <div style={{
            fontSize: '0.52rem', color: '#94a3b8', textTransform: 'uppercase',
            letterSpacing: '0.04em', marginBottom: 2,
          }}>
            Detected ({events.length})
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {events.slice(0, 3).map((e, i) => {
              const c = SEVERITY_COLOR[e.severity] || SEVERITY_COLOR.low
              return (
                <div key={i} style={{ display: 'flex', gap: 4, alignItems: 'flex-start' }}>
                  <span style={{
                    display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
                    background: c.dot, marginTop: 3, flexShrink: 0,
                  }} />
                  <span style={{ fontSize: '0.56rem', lineHeight: 1.4 }}>
                    <span style={{
                      color: c.fg, fontWeight: 600,
                      background: c.bg, borderRadius: 3, padding: '0 4px',
                      fontSize: '0.50rem', marginRight: 4,
                    }}>
                      {e.severity || '—'}
                    </span>
                    <strong style={{ color: '#334155' }}>{e.type}</strong>
                    {e.pid != null && e.pid !== -1 && (
                      <span style={{ color: '#64748b' }}> · pid {e.pid}</span>
                    )}
                    {e.detail && (
                      <span style={{ color: '#94a3b8' }}> — {e.detail}</span>
                    )}
                  </span>
                </div>
              )
            })}
            {events.length > 3 && (
              <div style={{ fontSize: '0.50rem', color: '#94a3b8' }}>
                +{events.length - 3} more event{events.length - 3 > 1 ? 's' : ''}
              </div>
            )}
          </div>
        </div>
      )}

      {proposal && (
        <div style={{ marginBottom: 4, flexShrink: 0 }}>
          <div style={{
            fontSize: '0.52rem', color: '#94a3b8', textTransform: 'uppercase',
            letterSpacing: '0.04em', marginBottom: 2,
          }}>
            Proposed (would not run)
          </div>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', alignItems: 'center' }}>
            <span className="pill" style={{ background: '#ede9fe', color: '#6d28d9' }}>
              {proposal?.proposed?.correction_type || '—'}
            </span>
            {proposal?.proposed?.new_scheduling_algorithm && (
              <span className="pill" style={{ background: '#dbeafe', color: '#1d4ed8' }}>
                → {proposal.proposed.new_scheduling_algorithm}
              </span>
            )}
          </div>
          {paramSummary(proposal?.proposed?.new_params) && (
            <div style={{
              fontSize: '0.50rem', color: '#b0b8cc', fontFamily: 'monospace',
              marginTop: 2, letterSpacing: '0.02em',
            }}>
              {paramSummary(proposal.proposed.new_params)}
            </div>
          )}
          {proposal?.proposed?.rationale && (
            <div style={{
              fontSize: '0.55rem', color: '#475569', lineHeight: 1.4,
              marginTop: 2, background: '#f8fafc',
              border: '1px solid #e2e8f0', borderRadius: 4,
              padding: '3px 6px',
            }}>
              {proposal.proposed.rationale}
            </div>
          )}
        </div>
      )}

      {decision && (
        <div style={{ flexShrink: 0 }}>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', alignItems: 'center' }}>
            <span className="pill" style={{
              background: accepted ? '#d1fae5' : '#fee2e2',
              color: accepted ? '#059669' : '#dc2626',
            }}>
              guard {String(decision.guard_result || '').toUpperCase()}
            </span>
            {decision.rejected_params && decision.rejected_params.length > 0 && (
              <span style={{ fontSize: '0.50rem', color: '#dc2626' }}>
                rejected: {decision.rejected_params.join(', ')}
              </span>
            )}
          </div>
          {decision.reason && (
            <div style={{
              fontSize: '0.55rem', color: '#64748b', marginTop: 2, lineHeight: 1.4,
            }}>
              {decision.reason}
            </div>
          )}
        </div>
      )}
    </Card>
  )
}
