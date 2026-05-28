/**
 * Header — minimal title + tabs + compact RUN.
 *
 * Per Page 1 second-revision goal §3 & §9:
 *   visible: title | tabs | RUN | small status pill
 *   removed: backend / profile / seed / offline form, algo selector,
 *            backend/workload/llm/algos/seed/events badges.
 *
 * The full run form is gone; the header RUN uses hardcoded demo-safe
 * defaults via the shared `useRun` hook so the existing run-server
 * pipeline keeps working.
 */
import { useRun } from '../data/useRun.js'

export default function Header({ tab, onTabChange, onRunComplete }) {
  const { available, state, inFlight, error, startRun } = useRun(onRunComplete)

  const TABS = ['LLM', 'Visualization', 'Evaluation']

  const pillClass = {
    IDLE: 'run-pill-idle', DONE: 'run-pill-ok', ERROR: 'run-pill-err',
    RUNNING: 'run-pill-run', PARSING: 'run-pill-run', EVALUATING: 'run-pill-run',
  }[state] || 'run-pill-idle'

  return (
    <div className="header-bar">
      <div className="header-title">LLM Sched Copilot</div>

      <nav className="header-tabs">
        {TABS.map(t => (
          <button
            key={t}
            className={`tab-btn ${tab === t ? 'active' : ''}`}
            onClick={() => onTabChange(t)}
          >
            {t}
          </button>
        ))}
      </nav>

      <div className="header-spacer" />

      {available === false && (
        <span className="run-pill run-pill-idle" title="Run server offline; start scripts/run_server.py">
          server offline
        </span>
      )}
      {available !== false && (
        <>
          <span className={`run-pill ${pillClass}`} title={error || state}>{state}</span>
          <button
            className="header-run-button"
            onClick={() => startRun()}
            disabled={inFlight || available === null}
            title="Trigger a new experiment (uses demo-safe defaults)"
          >
            RUN
          </button>
        </>
      )}
    </div>
  )
}
