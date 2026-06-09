/**
 * useRun — shared run-pipeline hook.
 *
 * Extracted from the original RunControls form (since removed) so the header
 * compact RUN button reuses the same execution path as before.
 * The big form was removed from Page 1; defaults below are hardcoded
 * for the demo-safe path. If finer control is needed later we can
 * surface a dev-only modal — the hook is the seam.
 */
import { useEffect, useRef, useState } from 'react'
import { startRun as apiStartRun, getStatus, healthCheck } from './runClient.js'

// RUN = the one honest path: a REAL local xv6 execution under QEMU, triggered
// through the local executor (scripts/run_server.py). This is the core project
// claim made live: "LLM suggests → Guard validates → xv6 executes."
//   - xv6 is the ONLY backend. There is no simulator and no offline-fixture
//     replay path — if the local executor / QEMU / RISC-V toolchain is not
//     running, RUN is disabled with a clear instruction rather than faking a
//     run by replaying already-finished data.
//   - The interactive profile is one of schedtest's curated xv6 tables.
const DEFAULTS = {
  backend: 'xv6',
  profile: 'interactive',
  seed: 42,
  run_all: true,
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
