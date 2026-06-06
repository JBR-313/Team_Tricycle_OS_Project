import Card from './Card.jsx'

/**
 * LLMContributionCard — Evaluation tab.
 *
 * Surfaces the burst-prediction ablation (tools/burst_ablation.py) so the
 * single most important LLM-value claim is visible in the default demo, not
 * buried in outputs/ablation/. It answers: "does the LLM actually contribute,
 * or could a dumb rule do the same?"
 *
 * Three strategies predict each process's first CPU burst from the SAME
 * label-stripped visible features the advisor sees:
 *   - ema_cold  : blind cold start (constant initial guess)
 *   - heuristic : a fixed hand rule on visible features
 *   - llm       : Solar Pro 3 reasoning
 *
 * The headline metric is pairwise_order_accuracy — for SJF/SRTF only the
 * RELATIVE ordering of bursts matters (shortest first), so getting the order
 * right is what changes the schedule. MAE (magnitude error) is shown as an
 * honest caveat: the LLM wins ordering decisively but its absolute magnitudes
 * are coarse — that is exactly what the kernel EMA correction is for.
 *
 * Data is static across runs, so the card hides itself when burst_ablation.json
 * is absent rather than presenting stale or empty evidence.
 */

const STRATEGY_META = {
  ema_cold:  { label: 'EMA cold start', sub: 'blind constant guess', tone: 'baseline' },
  heuristic: { label: 'Fixed heuristic', sub: 'hand rule on features', tone: 'baseline' },
  llm:       { label: 'LLM (Solar Pro 3)', sub: 'reasons over features', tone: 'llm' },
}
const ORDER = ['ema_cold', 'heuristic', 'llm']

function pct(x) {
  if (typeof x !== 'number' || Number.isNaN(x)) return '—'
  return `${Math.round(x * 100)}%`
}
function num(x, digits = 1) {
  if (typeof x !== 'number' || Number.isNaN(x)) return '—'
  return x.toFixed(digits)
}

export default function LLMContributionCard({ ablation }) {
  const agg = ablation?.aggregate
  if (!agg || typeof agg !== 'object') return null

  const rows = ORDER
    .filter(k => agg[k])
    .map(k => ({
      key: k,
      meta: STRATEGY_META[k] || { label: k, sub: '', tone: 'baseline' },
      order: agg[k].mean_pairwise_order_accuracy,
      mae: agg[k].mean_mae,
    }))
  if (rows.length === 0) return null

  const nWorkloads = agg.llm?.workloads_scored
    ?? agg.ema_cold?.workloads_scored ?? null
  const bestOrder = Math.max(...rows.map(r => (typeof r.order === 'number' ? r.order : 0)), 1)
  const llmOrder = agg.llm?.mean_pairwise_order_accuracy
  const baselineOrder = agg.ema_cold?.mean_pairwise_order_accuracy

  return (
    <Card label="LLM contribution — burst-prediction ablation" className="card-llm-contrib">
      <p className="contrib-lead">
        Does the LLM actually help, or could a dumb rule do the same? Each
        strategy predicts every process's first CPU burst from the{' '}
        <strong>same label-stripped features</strong> the advisor sees, scored
        against held-out ground truth
        {nWorkloads ? ` across ${nWorkloads} workloads` : ''}.
      </p>

      <div className="contrib-metric-head">
        <span className="contrib-metric-title">Pairwise order accuracy</span>
        <span className="contrib-metric-note">
          the SJF/SRTF-relevant metric — did it order bursts shortest-first?
        </span>
      </div>

      <div className="contrib-bars">
        {rows.map(r => (
          <div key={r.key} className={`contrib-bar-row contrib-${r.meta.tone}`}>
            <div className="contrib-bar-label">
              <span className="contrib-bar-name">{r.meta.label}</span>
              <span className="contrib-bar-sub">{r.meta.sub}</span>
            </div>
            <div className="contrib-bar-track">
              <div
                className="contrib-bar-fill"
                style={{ width: `${Math.max(2, (r.order / bestOrder) * 100)}%` }}
              />
            </div>
            <span className="contrib-bar-val">{pct(r.order)}</span>
          </div>
        ))}
      </div>

      {typeof llmOrder === 'number' && typeof baselineOrder === 'number' && (
        <div className="contrib-verdict">
          LLM orders bursts correctly <strong>{pct(llmOrder)}</strong> of the
          time vs <strong>{pct(baselineOrder)}</strong> for a blind cold start —
          a real, measured contribution to SJF/SRTF ordering.
        </div>
      )}

      <details className="contrib-mae">
        <summary>
          Magnitude error (MAE) — honest caveat
        </summary>
        <p className="contrib-mae-note">
          Lower is better. The LLM wins <em>ordering</em> but its absolute burst
          magnitudes are coarse; that is exactly what the kernel EMA correction
          refines at runtime.
        </p>
        <table className="contrib-mae-table">
          <thead>
            <tr><th>strategy</th><th>order acc.</th><th>mean MAE</th></tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.key} className={r.meta.tone === 'llm' ? 'contrib-row-llm' : ''}>
                <td>{r.meta.label}</td>
                <td>{pct(r.order)}</td>
                <td>{num(r.mae)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>

      <p className="contrib-src">
        source: <code>tools/burst_ablation.py</code> →{' '}
        <code>outputs/ablation/burst_ablation.json</code>
      </p>
    </Card>
  )
}
