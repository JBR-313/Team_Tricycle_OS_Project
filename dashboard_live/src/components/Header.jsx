/**
 * Header — minimal title + tabs + phase-aware primary RUN button.
 *
 * Presentational only: the staged-demo phase machine and the run pipeline live
 * in App. App passes the resolved button label / disabled state / status pill
 * and a single onRunClick handler that does the right thing for the current
 * phase (RUN ANALYSIS -> RUN VISUALIZATION -> VIEW EVALUATION).
 */
export default function Header({
  tab, onTabChange,
  runAvailable, runLabel, runDisabled, runPill, onRunClick,
}) {
  const TABS = ['LLM', 'Visualization', 'Evaluation']

  const pillClass = {
    IDLE: 'run-pill-idle', DONE: 'run-pill-ok', ERROR: 'run-pill-err',
    READY: 'run-pill-ok',
    ANALYZING: 'run-pill-run', REPLAYING: 'run-pill-run',
    RUNNING: 'run-pill-run', PARSING: 'run-pill-run', EVALUATING: 'run-pill-run',
  }[runPill] || 'run-pill-idle'

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

      {runAvailable === false && (
        <span className="run-pill run-pill-idle" title="Run server offline — analysis uses bundled data">
          server offline
        </span>
      )}
      <span className={`run-pill ${pillClass}`} title={runPill}>{runPill}</span>
      <button
        className="header-run-button"
        onClick={onRunClick}
        disabled={runDisabled}
        title="Staged demo: analysis → visualization → evaluation"
      >
        {runLabel}
      </button>
    </div>
  )
}
