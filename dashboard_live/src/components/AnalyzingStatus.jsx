import { useState, useEffect } from 'react'

/**
 * AnalyzingStatus — short animated status messages shown while the LLM is
 * "analyzing the workload" (first RUN). Cycles through a fixed list with an
 * animated ellipsis so the LLM tab visibly changes over time before the
 * recommendation is revealed. Frontend-only theatrics — no API streaming.
 */
const MESSAGES = [
  'Analyzing workload profile…',
  'Estimating CPU-bound vs I/O-bound behavior…',
  'Checking target metric…',
  'Comparing candidate scheduling algorithms…',
]

export default function AnalyzingStatus({ active }) {
  const [idx, setIdx] = useState(0)

  useEffect(() => {
    if (!active) return
    setIdx(0)
    const id = setInterval(() => {
      setIdx(i => Math.min(i + 1, MESSAGES.length - 1))
    }, 1100)
    return () => clearInterval(id)
  }, [active])

  if (!active) return null

  return (
    <div className="llm-analyzing" role="status" aria-live="polite">
      <span className="llm-analyzing-spinner" aria-hidden="true" />
      <div className="llm-analyzing-lines">
        {MESSAGES.slice(0, idx + 1).map((m, i) => (
          <div
            key={i}
            className={`llm-analyzing-line ${i === idx ? 'current' : 'done'}`}
          >
            {i < idx ? '✓ ' : ''}{m}
          </div>
        ))}
      </div>
    </div>
  )
}
