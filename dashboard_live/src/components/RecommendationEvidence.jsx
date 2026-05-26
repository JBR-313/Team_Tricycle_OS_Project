import Card from './Card.jsx'
import { getRecommendedAlgorithm, normalizeTargetMetric } from '../data/schemaCompat.js'

// Compact "Why this algorithm?" card. Read-only consolidation of fields
// the pipeline already publishes (recommendation, guard, workload_summary,
// metrics top-level). Every read is defensive — a missing field renders as
// "—" instead of crashing the dashboard.
export default function RecommendationEvidence({
  recommendation,
  guardDecision,
  workloadSummary,
  metrics,
  manifest,
}) {
  const rec = recommendation || {}
  const guard = guardDecision || {}
  const wl = workloadSummary || {}
  const m = metrics || {}
  const mf = manifest || {}

  const algo = getRecommendedAlgorithm(rec, '—')
  const target = (rec.target_metric || m.target_metric || mf.target_metric || '—')
    .replace?.(/_/g, ' ') || '—'

  const workloadLabel = mf.workload_type || mf.workload || wl.workload_type || wl.workload_file || '—'

  // Pick up to three workload traits the LLM is most likely keying off.
  const traits = []
  if (typeof wl.interactive_ratio === 'number') {
    traits.push(['interactive', `${Math.round(wl.interactive_ratio * 100)}%`])
  }
  if (wl.burst_count_distribution && typeof wl.burst_count_distribution.avg === 'number') {
    traits.push(['avg burst', wl.burst_count_distribution.avg.toFixed(2)])
  }
  if (typeof wl.avg_priority === 'number') {
    traits.push(['avg prio', String(wl.avg_priority)])
  }

  // Provenance — distinguish a real LLM call from the demo fallback.
  const llmModel = rec?._meta?.model
  const isDemoFallback = mf.metadata_source === 'demo_fallback'
  const provenance = isDemoFallback
    ? 'demo fallback (no LLM call)'
    : (llmModel ? `LLM: ${llmModel}` : '—')

  const recReason = rec.reason || '—'
  const guardResult = guard.guard_result ? String(guard.guard_result).toUpperCase() : '—'
  const guardReason = guard.reason || '—'
  const llmConfidence = typeof rec.confidence === 'number' ? rec.confidence.toFixed(2) : null
  const guardCompat = typeof guard.compatibility_score === 'number'
    ? guard.compatibility_score.toFixed(2) : null
  const guardConf = typeof guard.confidence_score === 'number'
    ? guard.confidence_score.toFixed(2) : null

  const judgment = m.judgment || '—'
  const regret = typeof m.regret_score === 'number' ? m.regret_score.toFixed(2) : '—'
  const jBg = { SUCCESS: '#d1fae5', 'NEAR-SUCCESS': '#dbeafe', FAIL: '#fee2e2' }[judgment] || '#f1f5f9'
  const jFg = { SUCCESS: '#059669', 'NEAR-SUCCESS': '#1d4ed8', FAIL: '#dc2626' }[judgment] || '#64748b'

  const guardAccepted = guard.guard_result === 'accepted'

  return (
    <Card label="Why this algorithm?" className="card-evidence">
      {/* Top row: workload → algorithm → target metric */}
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 4, flexShrink: 0 }}>
        <span className="pill" style={{ background: '#ede9fe', color: '#6d28d9', textTransform: 'capitalize' }}>
          {String(workloadLabel).replace(/_/g, ' ')}
        </span>
        <span style={{ fontSize: '0.55rem', color: '#94a3b8', alignSelf: 'center' }}>→</span>
        <span className="pill" style={{ background: '#ede9fe', color: '#6d28d9' }}>{algo}</span>
        <span className="pill" style={{ background: '#dbeafe', color: '#1d4ed8' }}>↳ {target}</span>
        {llmConfidence != null && (
          <span className="pill" style={{ background: '#f1f5f9', color: '#475569' }}>conf {llmConfidence}</span>
        )}
      </div>

      {/* Workload traits the LLM cites */}
      {traits.length > 0 && (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 4, flexShrink: 0 }}>
          {traits.map(([k, v]) => (
            <span key={k} className="pill" style={{ background: '#f1f5f9', color: '#475569', fontSize: '0.55rem' }}>
              {k} <strong style={{ color: '#334155' }}>{v}</strong>
            </span>
          ))}
        </div>
      )}

      {/* Full LLM reason — vertical scroll inside the card, no clipping. */}
      <div style={{
        fontSize: '0.60rem', color: '#334155', lineHeight: 1.5,
        background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 4,
        padding: '4px 6px', maxHeight: 60, overflowY: 'auto', marginBottom: 4,
      }}>
        <span style={{ color: '#94a3b8', fontWeight: 600 }}>LLM:</span> {recReason}
      </div>

      {/* Guard verdict */}
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 4, flexShrink: 0 }}>
        <span className="pill" style={{
          background: guardAccepted ? '#d1fae5' : '#fee2e2',
          color: guardAccepted ? '#059669' : '#dc2626',
        }}>
          guard {guardResult}
        </span>
        {guardCompat != null && (
          <span className="pill" style={{ background: '#f1f5f9', color: '#475569' }}>compat {guardCompat}</span>
        )}
        {guardConf != null && (
          <span className="pill" style={{ background: '#f1f5f9', color: '#475569' }}>conf {guardConf}</span>
        )}
      </div>
      <div style={{
        fontSize: '0.56rem', color: '#64748b', lineHeight: 1.45,
        background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 4,
        padding: '3px 6px', maxHeight: 36, overflowY: 'auto', marginBottom: 4,
      }}>
        <span style={{ color: '#94a3b8', fontWeight: 600 }}>Guard:</span> {guardReason}
      </div>

      {/* Bottom: provenance + final metric judgment */}
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', flexShrink: 0 }}>
        <span className="pill" style={{
          background: isDemoFallback ? '#fef3c7' : '#f1f5f9',
          color: isDemoFallback ? '#b45309' : '#475569',
          fontSize: '0.55rem',
        }}>
          {provenance}
        </span>
        <span className="pill" style={{ background: jBg, color: jFg }}>{judgment}</span>
        {regret !== '—' && (
          <span className="pill" style={{ background: '#f1f5f9', color: '#64748b' }}>regret {regret}</span>
        )}
      </div>
    </Card>
  )
}
