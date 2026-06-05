import Card from './Card.jsx'
import Typewriter from './Typewriter.jsx'

/**
 * LLMExplanation — Page 1 §4 (pre-execution only).
 *
 * Sections:
 *   Summary           — short pre-execution recommendation sentence
 *   Expected behavior — algorithm-characteristic template (pre-execution)
 *   Trade-off         — algorithm-characteristic risk (pre-execution)
 *   Caution           — actionable tuning note (pre-execution)
 *
 * Hard rule (goal §0 / §4):
 *   This card is rendered on Page 1 and Page 1 is the pre-execution page.
 *   It MUST NOT use `trace_explanation.json` (post-execution evidence
 *   like "first ran at tick 2", "demoted at tick 10", "performed well").
 *   Content is derived from `recommendation` + `workloadSummary` only.
 */

/* Static, pre-execution algorithm templates. Each entry yields short
 * sentences in pre-execution voice ("should", "is expected to"). */
const ALGO_TEMPLATES = {
  MLFQ: {
    behavior: 'Short jobs should receive CPU quickly in upper queues, while longer jobs continue in lower queues.',
    tradeoff: 'Poorly tuned aging may delay long CPU-bound jobs.',
    caution:  'If CPU-bound jobs increase, lower the aging threshold or adjust queue quanta.',
  },
  SJF: {
    behavior: 'Shorter predicted bursts are expected to run first, reducing average waiting time.',
    tradeoff: 'Long jobs may starve when many short jobs keep arriving.',
    caution:  'Burst prediction quality determines outcome — EMA needs a few observed bursts to stabilise.',
  },
  SRTF: {
    behavior: 'Shorter remaining predicted time should preempt longer jobs for faster response.',
    tradeoff: 'Long jobs may starve, and frequent preemption can hurt throughput.',
    caution:  'Large burst-prediction error can degrade behaviour; verify the predictor is consistent.',
  },
  PRIORITY: {
    behavior: 'Higher-priority jobs are expected to run first; aging gradually raises long-waiting jobs.',
    tradeoff: 'Low-priority jobs may starve without strong aging.',
    caution:  'If aging is too weak, low-priority CPU-bound jobs may wait excessively.',
  },
  RR: {
    behavior: 'Each runnable job should receive an equal time slice in turn.',
    tradeoff: 'A small quantum wastes CPU on context switches; a large quantum hurts response time.',
    caution:  'Workloads with widely varying burst lengths may not be served evenly by a single quantum.',
  },
  FCFS: {
    behavior: 'Jobs should run to completion in arrival order, without preemption.',
    tradeoff: 'A long job arriving first creates a convoy that delays everything behind it.',
    caution:  'Suitable only for similar-burst batch workloads; avoid when interactive jobs are present.',
  },
}

function workloadCharacter(wl) {
  if (!wl) return null
  const cpu = wl.cpu_bound_ratio
  const ia  = wl.interactive_ratio
  if (typeof cpu !== 'number' && typeof ia !== 'number') return null
  if (ia >= 0.7) return 'interactive-heavy'
  if (cpu >= 0.6) return 'CPU-bound'
  if (typeof ia === 'number' && typeof cpu === 'number'
      && Math.abs(ia - cpu) < 0.2) return 'mixed CPU and interactive'
  if (ia >= cpu) return 'lean toward interactive'
  return 'lean toward CPU-bound'
}

function targetMetricPhrase(t) {
  if (!t) return null
  const clean = t.replace(/_/g, ' ').replace(/^avg /, 'average ').toLowerCase()
  return `${clean}-sensitive`
}

export default function LLMExplanation({ recommendation, workloadSummary, show = true, typing = false }) {
  const rec = recommendation || {}
  const wl  = workloadSummary || {}
  const algo = (rec.recommended_scheduling_algorithm || rec.algorithm || '').toUpperCase()

  if (!show) {
    return (
      <Card label="LLM Explanation" className="card-expl page1-card page1-card-expl">
        <div className="llm-placeholder">
          <span className="llm-placeholder-dots"><i /><i /><i /></span>
          <span className="llm-placeholder-text">Preparing explanation…</span>
        </div>
      </Card>
    )
  }

  if (!algo) {
    return (
      <Card label="LLM Explanation" className="card-expl page1-card page1-card-expl">
        <div className="loading">Loading…</div>
      </Card>
    )
  }

  const tmpl = ALGO_TEMPLATES[algo] || ALGO_TEMPLATES.RR

  // Summary — synthesised, pre-execution voice. Reads the workload's visible
  // character and the target metric; never mentions tick numbers or results.
  const character = workloadCharacter(wl)
  const target = targetMetricPhrase(rec.target_metric || wl.target_metric)
  const summaryParts = [`${algo} is recommended`]
  if (character && target) summaryParts.push(`because the workload appears ${character} and ${target}.`)
  else if (character)      summaryParts.push(`for this ${character} workload.`)
  else if (target)         summaryParts.push(`for a ${target} workload.`)
  else                     summaryParts.push('for this workload.')
  const summary = summaryParts.join(' ')

  // Caution: prefer LLM-provided risks if present, else fall back to template.
  const risks = Array.isArray(rec.risks)
    ? rec.risks.filter(r => typeof r === 'string').slice(0, 2)
    : []
  const cautionLines = risks.length > 0
    ? risks.map(r => r.replace(/_/g, ' '))
    : [tmpl.caution]

  return (
    <Card label="LLM Explanation" className="card-expl page1-card page1-card-expl">
      <section className="page1-section">
        <h4 className="page1-section-title">Summary</h4>
        <p className="page1-body">
          {typing ? <Typewriter text={summary} start speed={14} /> : summary}
        </p>
      </section>

      <section className="page1-section">
        <h4 className="page1-section-title">Expected behavior</h4>
        <p className="page1-body">{tmpl.behavior}</p>
      </section>

      <section className="page1-section">
        <h4 className="page1-section-title">Trade-off</h4>
        <p className="page1-body">{tmpl.tradeoff}</p>
      </section>

      <section className="page1-section page1-section-caution">
        <h4 className="page1-section-title">Caution</h4>
        {cautionLines.length === 1
          ? <p className="page1-body">{cautionLines[0]}</p>
          : (
            <ul className="page1-bullets">
              {cautionLines.map((c, i) => <li key={i}>{c}</li>)}
            </ul>
          )}
      </section>
    </Card>
  )
}
