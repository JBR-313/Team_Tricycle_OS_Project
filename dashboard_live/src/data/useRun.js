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

// Default RUN = xv6 PRIMARY path. This is the core project claim:
//   "LLM suggests → Guard validates → xv6 executes."
// The interactive profile is one of schedtest's curated xv6 tables. Simulator
// and offline-fixture remain available but only as EXPLICIT fallbacks (pass
// overrides via startRun({ backend:'simulator', offline_fixture:true })).
// If the run-server / QEMU / RISC-V toolchain is unavailable the run errors
// with a clear message instead of silently degrading to the simulator.
const DEFAULTS = {
  backend: 'xv6',
  profile: 'interactive',
  seed: 42,
  run_all: true,
  offline_fixture: false,
}

// Explicit fallback presets (dev-only). Never used automatically.
export const FALLBACK_PRESETS = {
  SIMULATOR: { backend: 'simulator', profile: 'ambiguous_mixed', offline_fixture: false },
  OFFLINE:   { backend: 'simulator', profile: 'ambiguous_mixed', offline_fixture: true },
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
