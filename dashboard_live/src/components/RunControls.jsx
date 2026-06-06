import { useEffect, useRef, useState } from 'react'
import Card from './Card.jsx'
import { startRun, getStatus, healthCheck } from '../data/runClient.js'

/**
 * RunControls — RUN button + run-state badge.
 *
 * Polls /api/status every 750 ms while a run is in flight; calls onRunComplete()
 * once the state transitions to DONE so the parent can reload live-data.
 * Hides entirely if the run-server is unreachable, so dashboards without a
 * server still render cleanly (snapshot-only mode).
 */
export default function RunControls({ onRunComplete }) {
  const [available, setAvailable]   = useState(null) // null=checking, true/false=known
  const [status, setStatus]         = useState(null)
  const [backend, setBackend]       = useState('simulator')
  const [profile, setProfile]       = useState('ambiguous_mixed')
  const [seed, setSeed]             = useState(42)
  const [offlineFixture, setOffline]= useState(true)
  const [err, setErr]               = useState(null)
  const [lastRoll, setLastRoll]     = useState(null)
  const pollRef = useRef(null)
  const lastStateRef = useRef('IDLE')

  // ── Probe run-server availability ─────────────────────────────────────────
  useEffect(() => {
    let alive = true
    healthCheck().then(h => {
      if (!alive) return
      setAvailable(!!h?.ok)
      if (h?.ok) {
        getStatus().then(setStatus).catch(() => {})
      }
    })
    return () => { alive = false }
  }, [])

  // ── Poll while RUNNING ────────────────────────────────────────────────────
  useEffect(() => {
    if (!available) return
    const tick = async () => {
      try {
        const s = await getStatus()
        setStatus(s)
        if (s.state === 'DONE' && lastStateRef.current !== 'DONE') {
          onRunComplete && onRunComplete()
        }
        lastStateRef.current = s.state
      } catch (e) {
        // transient; keep polling
      }
    }
    pollRef.current = setInterval(tick, 750)
    return () => clearInterval(pollRef.current)
  }, [available, onRunComplete])

  if (available === null) return null
  if (available === false) {
    return (
      <Card label="Run Experiment" className="card-run">
        <div className="run-row">
          <span className="run-badge run-badge-idle">Run server offline</span>
          <span className="run-hint">Start: <code>python3 scripts/run_server.py</code></span>
        </div>
      </Card>
    )
  }

  const state = status?.state || 'IDLE'
  const inFlight = !['IDLE', 'DONE', 'ERROR'].includes(state)

  const PROFILES_SIM = [
    'interactive_heavy', 'short_jobs_clustered', 'long_job_first_convoy',
    'interactive_mixed', 'priority_critical_tasks', 'starvation_risk',
    'cpu_bound_vs_io_bound', 'ambiguous_mixed', 'pure_batch', 'bursty_long_tail',
  ]
  const PROFILES_XV6 = [
    'interactive', 'cpu_bound', 'mixed', 'priority_sensitive',
  ]
  const profileList = backend === 'xv6' ? PROFILES_XV6 : PROFILES_SIM
  const RANDOM = '🎲 random'

  async function handleRun() {
    setErr(null)
    // 🎲 random: roll a fresh profile AND seed so every press is a different
    // run. On the simulator a new seed re-jitters the workload instance; on
    // xv6 the seed is fixed-by-profile so only the profile changes.
    let runProfile = profileList.includes(profile) ? profile : profileList[0]
    let runSeed = Number(seed)
    if (profile === RANDOM) {
      runProfile = profileList[Math.floor(Math.random() * profileList.length)]
      runSeed = Math.floor(Math.random() * 100000)
      setLastRoll(`rolled ${runProfile} · seed ${runSeed}`)
    } else {
      setLastRoll(null)
    }
    try {
      await startRun({
        backend,
        profile: runProfile,
        seed: runSeed,
        run_all: true,
        offline_fixture: offlineFixture,
      })
      // optimistic — actual state will reflect on next poll
      setStatus(s => ({ ...(s || {}), state: 'RUNNING', stage: 'starting' }))
    } catch (e) {
      setErr(e.message)
    }
  }

  const badgeClass = {
    IDLE: 'run-badge-idle', DONE: 'run-badge-ok', ERROR: 'run-badge-err',
    RUNNING: 'run-badge-run', PARSING: 'run-badge-run', EVALUATING: 'run-badge-run',
  }[state] || 'run-badge-idle'

  return (
    <Card label="Run Experiment" className="card-run">
      <div className="run-row">
        <span className={`run-badge ${badgeClass}`}>{state}</span>
        {status?.stage && <span className="run-stage">{status.stage}</span>}
      </div>

      <div className="run-controls">
        <label>
          backend
          <select value={backend} onChange={e => setBackend(e.target.value)} disabled={inFlight}>
            <option value="simulator">simulator</option>
            <option value="xv6">xv6</option>
          </select>
        </label>
        <label>
          profile
          <select value={profile} onChange={e => setProfile(e.target.value)} disabled={inFlight}>
            <option value={RANDOM}>{RANDOM}</option>
            {profileList.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <label>
          seed
          <input type="number" min="0" value={seed}
                 onChange={e => setSeed(e.target.value)}
                 disabled={inFlight || profile === RANDOM}
                 title={profile === RANDOM ? 'seed is rolled randomly' : undefined} />
        </label>
        <label className="run-checkbox">
          <input type="checkbox" checked={offlineFixture}
                 onChange={e => setOffline(e.target.checked)} disabled={inFlight} />
          offline-fixture (no LLM call)
        </label>
        <button className="run-button" onClick={handleRun} disabled={inFlight}>
          {inFlight ? '…' : 'RUN'}
        </button>
      </div>

      {lastRoll && <div className="run-hint">🎲 {lastRoll}</div>}
      {err && <div className="run-error">⚠ {err}</div>}

      {status?.log_tail?.length > 0 && (
        <details className="run-log">
          <summary>log ({status.log_tail.length} lines)</summary>
          <pre>{status.log_tail.slice(-12).join('\n')}</pre>
        </details>
      )}
    </Card>
  )
}
