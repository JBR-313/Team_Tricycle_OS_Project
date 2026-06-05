import { useState, useEffect } from 'react'

/**
 * Typewriter — reveals `text` character-by-character when `start` is true,
 * imitating an LLM generating an answer. When `start` is false the full text
 * is shown immediately (e.g. after the reveal stage has already passed, so a
 * later re-render does not re-animate).
 *
 * Purely presentational: there is no real API streaming. The text is the
 * already-generated static recommendation/explanation; we only animate how it
 * appears so the demo reads like a chatbot response.
 */
export default function Typewriter({ text, speed = 16, start = true, className }) {
  const full = typeof text === 'string' ? text : ''
  const [n, setN] = useState(start ? 0 : full.length)

  useEffect(() => {
    if (!start) { setN(full.length); return }
    setN(0)
    if (!full) return
    let i = 0
    const id = setInterval(() => {
      i += 1
      setN(i)
      if (i >= full.length) clearInterval(id)
    }, speed)
    return () => clearInterval(id)
  }, [full, start, speed])

  const done = n >= full.length
  return (
    <span className={className}>
      {full.slice(0, n)}
      {start && !done && <span className="tw-caret" aria-hidden="true">▋</span>}
    </span>
  )
}
