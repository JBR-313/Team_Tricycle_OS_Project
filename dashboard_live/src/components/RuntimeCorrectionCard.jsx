import Card from './Card.jsx'

/**
 * RuntimeCorrectionCard — Evaluation tab (POST-execution).
 *
 * Honestly surfaces the host-side post-evaluation correction apply loop result
 * from correction_applied.json. This is NOT live kernel control: when the
 * original run is judged FAIL/starvation, the orchestrator re-runs xv6 with a
 * corrected, Guard-approved algorithm and records the before/after here.
 *
 * Three honest states:
 *   - no data            → card hidden (returns null)
 *   - applied:false      → "No correction applied" + reason (e.g. SUCCESS)
 *   - applied:true       → before/after comparison with an improved badge
 */
function fmt(v) {
  if (v == null) return 'N/A'
  return typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(2)) : String(v)
}

export default function RuntimeCorrectionCard({ correction }) {
  if (!correction) return null

  if (correction.applied === false) {
    return (
      <Card label="Runtime Correction (post-run)" className="card-correction">
        <div className="correction-none">
          <span className="correction-tag correction-tag-none">NO CORRECTION</span>
          <p className="correction-reason">{correction.reason || 'No correction was applied.'}</p>
        </div>
      </Card>
    )
  }

  if (correction.applied === true) {
    const {
      original_algorithm, corrected_algorithm, target_metric,
      original_metric_value, corrected_metric_value, improved,
      original_judgment, corrected_judgment, trigger, forced,
    } = correction
    return (
      <Card label="Runtime Correction (post-run)" className="card-correction">
        <div className="correction-applied">
          <span className={`correction-tag ${improved ? 'correction-tag-good' : 'correction-tag-warn'}`}>
            {improved ? 'CORRECTION IMPROVED' : 'CORRECTION APPLIED'}
          </span>
          <span className="correction-trigger" title="why the correction fired">
            {forced ? 'forced' : (trigger || 'fail')}
          </span>
        </div>
        <div className="correction-flow">
          <div className="correction-side">
            <span className="correction-side-label">Before</span>
            <span className="correction-algo">{original_algorithm}</span>
            <span className="correction-val">{fmt(original_metric_value)}</span>
            <span className="correction-judg">{original_judgment}</span>
          </div>
          <span className="correction-arrow">→</span>
          <div className="correction-side correction-side-after">
            <span className="correction-side-label">After</span>
            <span className="correction-algo">{corrected_algorithm}</span>
            <span className="correction-val">{fmt(corrected_metric_value)}</span>
            <span className="correction-judg">{corrected_judgment}</span>
          </div>
        </div>
        <p className="correction-metric-note">
          Target metric: <strong>{target_metric}</strong> · re-ran the real xv6
          kernel with the corrected algorithm (host-side, post-evaluation).
        </p>
      </Card>
    )
  }

  return null
}
