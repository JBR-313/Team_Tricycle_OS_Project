export default function Header({
  algo, onAlgoChange, ALGOS,
  currentTick, maxTick, onTickChange,
  focusMode, onFocusModeChange,
  fixture,
}) {
  const FOCUS_MODES = [
    { id: 'hero',         label: 'Hero' },
    { id: 'full',         label: 'Full' },
    { id: 'process-flow', label: 'Flow' },
    { id: 'gantt',        label: 'Gantt' },
    { id: 'trace',        label: 'Trace' },
    { id: 'metrics',      label: 'Metrics' },
  ]

  return (
    <div className="header-bar">
      <div className="header-brand">
        <div className="header-dot" />
        <div>
          <div className="header-title">LLM Sched Copilot</div>
          <div className="header-subtitle">
            {fixture ? `fixture: ${fixture.replace(/_/g, ' ')}` : 'UI Lab · Static Fixture'}
          </div>
        </div>
      </div>

      <div className="header-spacer" />

      <div className="header-mode-pills">
        {FOCUS_MODES.map(m => (
          <button
            key={m.id}
            className={`header-mode-pill ${focusMode === m.id ? 'active' : ''}`}
            onClick={() => onFocusModeChange(m.id)}
          >
            {m.label}
          </button>
        ))}
      </div>

      <div className="header-spacer" />

      <span className="header-algo-label">Algorithm</span>
      <select
        className="algo-select"
        value={algo}
        onChange={e => onAlgoChange(e.target.value)}
      >
        {(ALGOS || []).map(a => (
          <option key={a} value={a}>{a}</option>
        ))}
      </select>

      <div className="header-spacer" />

      <span className="header-tick-label">Tick</span>
      <span className="header-tick-val">
        {currentTick}
        <span className="header-tick-max">/ {maxTick}</span>
      </span>
      <input
        type="range"
        className="tick-slider"
        min={0}
        max={maxTick}
        value={currentTick}
        onChange={e => onTickChange(Number(e.target.value))}
      />
    </div>
  )
}
