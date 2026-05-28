/**
 * useRun — shared run-pipeline hook.
 *
 * Extracted from RunControls so the header compact RUN button (Page 1
 * second-revision goal §3) reuses the same execution path as before.
 * The big form was removed from Page 1; defaults below are hardcoded
 * for the demo-safe path. If finer control is needed later we can
 * surface a dev-only modal — the hook is the seam.
 */
import { useEffect, useRef, useState } from 'react'
import { startRun as apiStartRun, getStatus, healthCheck } from './runClient.js'

const DEFAULTS = {
  backend: 'simulator',
  profile: 'ambiguous_mixed',
  seed: 42,
  run_all: true,
  offline_fixture: true,   // safest: doesn't require a Solar API key
}

export function useRun(onComplete) {
  const [available, setAvailable] = useState(null)  // null | true | false
  const [status, setStatus]       = useState(null)
  const [error, setError]         = useState(null)
  const pollRef        = useRef(null)
  const lastStateRef   = useRef('IDLE')

  // Probe run-server availability once.
  useEffect(() => {
    let alive = true
    healthCheck().then(h => {
      if (!alive) return
      setAvailable(!!h?.ok)
      if (h?.ok) getStatus().then(setStatus).catch(() => {})
    })
    return () => { alive = false }
  }, [])

  // Poll while in flight.
  useEffect(() => {
    if (!available) return
    const tick = async () => {
      try {
        const s = await getStatus()
        setStatus(s)
        if (s.state === 'DONE' && lastStateRef.current !== 'DONE') {
          onComplete && onComplete()
        }
        lastStateRef.current = s.state
      } catch { /* silent */ }
    }
    pollRef.current = setInterval(tick, 750)
    return () => clearInterval(pollRef.current)
  }, [available, onComplete])

  async function startRun(overrides = {}) {
    setError(null)
    try {
      await apiStartRun({ ...DEFAULTS, ...overrides })
      setStatus(s => ({ ...(s || {}), state: 'RUNNING', stage: 'starting' }))
    } catch (e) {
      setError(e.message)
    }
  }

  const state = status?.state || 'IDLE'
  const inFlight = !['IDLE', 'DONE', 'ERROR'].includes(state)

  return { available, state, inFlight, status, error, startRun, defaults: DEFAULTS }
}
