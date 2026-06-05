import Card from './Card.jsx'

/**
 * TraceExplanationCard — Evaluation tab (POST-execution).
 *
 * Renders the LLM's natural-language explanation of the FINISHED run from
 * trace_explanation.json. Unlike LLMExplanation.jsx (Page 1, pre-execution
 * templates), this card is allowed to reference real trace evidence because
 * it is shown only after the run completes.
 *
 * The orchestrator writes a fresh explanation per run, or an explicit
 * `available: false` placeholder when the LLM could not be called (e.g. no
 * API key). We honor that: never present a stale or empty explanation as if
 * it described the current run.
 */
export default function TraceExplanationCard({ explanation }) {
  const exp = explanation || {}

  // Explicit unavailable placeholder (or nothing loaded) → calm honest note.
  if (!explanation || exp.available === false) {
    const reason = exp.reason
      || 'No trace explanation was generated for this run.'
    return (
      <Card label="LLM Explanation (post-run)" className="card-trace-expl">
        <div className="trace-expl-unavailable">
          <span className="trace-expl-na-tag">NOT AVAILABLE</span>
          <p className="trace-expl-na-text">{reason}</p>
          <p className="trace-expl-na-hint">
            Run the pipeline with a valid <code>UPSTAGE_API_KEY</code> to get a
            fresh natural-language explanation of this run.
          </p>
        </div>
      </Card>
    )
  }

  const evidence = Array.isArray(exp.evidence)
    ? exp.evidence.filter(e => typeof e === 'string' && e.trim())
    : []
  const source = exp.source || (exp._meta && exp._meta.source) || 'llm'
  const sourceLabel = source === 'demo_fallback' ? 'demo fixture' : 'live LLM'

  return (
    <Card label="LLM Explanation (post-run)" className="card-trace-expl">
      {exp.detected_pattern && (
        <div className="trace-expl-pattern">
          <span className="trace-expl-pattern-tag">{exp.detected_pattern}</span>
          {exp.scheduling_algorithm && (
            <span className="trace-expl-algo">{exp.scheduling_algorithm}</span>
          )}
          <span className="trace-expl-source" title={`Explanation source: ${sourceLabel}`}>
            {sourceLabel}
          </span>
        </div>
      )}

      {exp.summary && (
        <section className="trace-expl-section">
          <h4 className="trace-expl-title">Summary</h4>
          <p className="trace-expl-body">{exp.summary}</p>
        </section>
      )}

      {exp.main_reason && (
        <section className="trace-expl-section">
          <h4 className="trace-expl-title">Main reason</h4>
          <p className="trace-expl-body">{exp.main_reason}</p>
        </section>
      )}

      {evidence.length > 0 && (
        <section className="trace-expl-section">
          <h4 className="trace-expl-title">Evidence</h4>
          <ul className="trace-expl-bullets">
            {evidence.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </section>
      )}

      {exp.suggestion && (
        <section className="trace-expl-section trace-expl-section-suggest">
          <h4 className="trace-expl-title">Suggestion</h4>
          <p className="trace-expl-body">{exp.suggestion}</p>
        </section>
      )}
    </Card>
  )
}
