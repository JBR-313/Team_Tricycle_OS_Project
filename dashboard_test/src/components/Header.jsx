export default function Header({
  algo, onAlgoChange, ALGOS,
  currentTick, maxTick, onTickChange,
  step, onStepChange,
}) {
  const STEPS = ['Recommend', 'Execute', 'Evaluate']

  return (
    <div className="header-bar">
      <div className="header-brand">
        <div className="header-dot" />
        <div>
          <div className="header-title">LLM Sched Copilot</div>
          <div className="header-subtitle">
            LLM suggests · Guard validates · xv6 executes · Metrics verify
          </div>
        </div>
      </div>

      <div className="header-spacer" />

      {/* Step navigation */}
      <div className="header-steps">
        {STEPS.map((s, i) => (
          <button
            key={s}
            className={`header-step-btn ${step === s ? 'active' : ''}`}
            onClick={() => onStepChange(s)}
          >
            <span className="step-num">{i + 1}</span>
            {s}
          </button>
        ))}
      </div>

      <div className="header-spacer" />

      <span className="header-mode-badge">SIMULATOR</span>

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
