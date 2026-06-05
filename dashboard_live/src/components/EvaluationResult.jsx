import Card from './Card.jsx'
import { isHigherBetterMetric, normalizeTargetMetric } from '../data/schemaCompat.js'

/**
 * EvaluationResult — Page 3 hero card.
 *
 * Shows, in this order, with the verdict dominant:
 *   1. Verdict (SUCCESS / NEAR-SUCCESS / FAIL)
 *   2. One-sentence summary: "LLM selected X, and X was also the best …"
 *   3. Target metric  |  LLM selected  |  Best algorithm
 *   4. Regret %       |  Starvation
 *
 * No tiny chip rail across the top, no abbreviation jargon. Same
 * readability standard as Page 1 / Page 2.
 */

const VERDICT_STYLE = {
  SUCCESS:        { bg: '#d1fae5', fg: '#047857', border: '#34d399' },
  'NEAR-SUCCESS': { bg: '#dbeafe', fg: '#1e40af', border: '#60a5fa' },
  FAIL:           { bg: '#fee2e2', fg: '#b91c1c', border: '#f87171' },
  UNKNOWN:        { bg: '#f1f5f9', fg: '#475569', border: '#cbd5e1' },
}

function formatRegret(r) {
  if (r == null) return null
  const pct = r * 100
  if (pct >= 999.5) return '>999% (best ≈ 0)'
  if (pct < 1) return `${pct.toFixed(2)}%`
  return `${pct.toFixed(1)}%`
}

function prettyMetric(key) {
  return (key || 'avg_response_time')
    .replace(/_/g, ' ')
    .replace(/^avg /, 'Avg ')
    .replace(/\b\w/g, c => c.toUpperCase())
}

export default function EvaluationResult({ metrics, recommendation: rec }) {
  if (!metrics || !rec) {
    return (
      <Card label="Evaluation Result" className="card-eval">
        <div className="loading">Loading…</div>
      </Card>
    )
  }

  // No live data: do not imply a failed run — show a calm, honest empty state.
  if (metrics.no_data) {
    return (
      <Card label="Evaluation Result" className="card-eval">
        <div className="eval-nodata">
          <span className="eval-nodata-tag">NO DATA</span>
          <p className="eval-nodata-text">
            No live trace data available. Run the xv6 pipeline or select a
            snapshot to evaluate a scheduling run.
          </p>
        </div>
      </Card>
    )
  }

  const verdict = metrics.judgment || 'UNKNOWN'
  const vStyle  = VERDICT_STYLE[verdict] || VERDICT_STYLE.UNKNOWN
  const regret  = formatRegret(metrics.regret_score)
  const starv   = metrics.starvation_occurred
  const cmp     = metrics.comparison || {}
  const recAlgo = rec.recommended_scheduling_algorithm || rec.algorithm || '—'
  const tgtKey  = normalizeTargetMetric(rec.target_metric || 'avg_response_time')
  const tgtPretty = prettyMetric(tgtKey)
  const higher  = isHigherBetterMetric(tgtKey)

  let bestAlgo = '—', bestVal = higher ? -Infinity : Infinity
  for (const [a, v] of Object.entries(cmp)) {
    const val = v?.[tgtKey]
    if (typeof val === 'number' && (higher ? val > bestVal : val < bestVal)) {
      bestVal = val
      bestAlgo = a
    }
  }
  if (!Number.isFinite(bestVal)) { bestAlgo = '—'; bestVal = null }

  // Summary sentence — direct, complete-sentence.
  const sameAsBest = bestAlgo !== '—' && bestAlgo === recAlgo
  let summary
  if (sameAsBest) {
    summary = `LLM selected ${recAlgo}, and ${recAlgo} was also the best algorithm for ${tgtPretty.toLowerCase()}.`
  } else if (bestAlgo !== '—') {
    summary = `LLM selected ${recAlgo}; the best algorithm for ${tgtPretty.toLowerCase()} was ${bestAlgo}.`
  } else {
    summary = `LLM selected ${recAlgo}. Best algorithm could not be determined from the current comparison.`
  }

  return (
    <Card label="Evaluation Result" className="card-eval eval-card">
      <div
        className="eval-verdict-box"
        style={{ background: vStyle.bg, borderColor: vStyle.border, color: vStyle.fg }}
      >
        <span className="eval-verdict-word">{verdict}</span>
        {regret != null && (
          <span className="eval-verdict-regret">Regret {regret}</span>
        )}
      </div>

      <p className="eval-summary">{summary}</p>

      <div className="eval-target-box">
        <span className="eval-target-label">Target Metric</span>
        <span className="eval-target-value">{tgtPretty}</span>
      </div>

      <dl className="eval-fact-grid eval-fact-grid-3">
        <div>
          <dt>LLM Selected</dt>
          <dd className="eval-fact-llm">{recAlgo}</dd>
        </div>
        <div>
          <dt>Best Algorithm</dt>
          <dd className={sameAsBest ? 'eval-fact-best-match' : 'eval-fact-best'}>
            {bestAlgo}
          </dd>
        </div>
        <div>
          <dt>Starvation</dt>
          <dd className={starv ? 'eval-fact-starv' : 'eval-fact-ok'}>
            {starv ? 'Yes — process(es) never ran' : 'None'}
          </dd>
        </div>
      </dl>
    </Card>
  )
}
