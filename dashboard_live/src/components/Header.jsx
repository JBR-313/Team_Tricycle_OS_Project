import { ALGOS } from '../data/liveDataClient.js'

export default function Header({
  algo, onAlgoChange,
  currentTick, maxTick, onTickChange,
  liveMode, onLiveModeToggle,
  dataStatus,
}) {
  return (
    <div className="header-bar">
      <div className="header-brand">
        <div className="header-dot" />
        <div>
          <div className="header-title">LLM Sched Copilot <span style={{ fontSize: '0.65rem', color: '#94a3b8' }}>LIVE</span></div>
          <div className="header-subtitle">
            LLM suggests · Guard validates · xv6 executes · Metrics verify
          </div>
        </div>
      </div>

      <div className="header-spacer" />

      {/* Data status indicator */}
      <div className={`header-data-status${dataStatus.mode === 'fallback' ? ' ds-warn' : ''}`}>
        <span className={`ds-mode${dataStatus.mode === 'fallback' ? ' ds-mode-fallback' : ''}`}>
          {dataStatus.mode}
        </span>
        {dataStatus.manifestVersion != null && (
          <span className="ds-version" title="Manifest version">v{dataStatus.manifestVersion}</span>
        )}
        {dataStatus.updatedAt && (
          <span className="ds-time">{dataStatus.updatedAt}</span>
        )}
        {liveMode && (
          <span className="ds-live-dot" title="Live polling active" />
        )}
        {!liveMode && dataStatus.mode !== 'loading' && (
          <span className="ds-polling-off" title="Live polling off">■</span>
        )}
        {dataStatus.traceErrors && Object.keys(dataStatus.traceErrors).length > 0 && (
          <span
            className="ds-trace-err"
            title={`Trace parse errors:\n${Object.entries(dataStatus.traceErrors).map(([k,v])=>`${k}: ${v}`).join('\n')}`}
          >
            ⚠ {Object.keys(dataStatus.traceErrors).join(',')}
          </span>
        )}
      </div>

      {/* Fallback warning banner */}
      {dataStatus.mode === 'fallback' && (
        <div className="ds-fallback-banner">
          No live data — showing fallback. Run <code>python3 scripts/run_live_dashboard_pipeline.py</code>
        </div>
      )}

      <div className="header-spacer" />

      <span className="header-algo-label">Algorithm</span>
      <select
        className="algo-select"
        value={algo}
        onChange={e => onAlgoChange(e.target.value)}
      >
        {ALGOS.map(a => (
          <option key={a} value={a}>{a}</option>
        ))}
      </select>

      <div className="header-spacer" />

      {/* Replay / Live toggle */}
      <div className="mode-toggle">
        <button
          className={`mode-btn ${!liveMode ? 'active' : ''}`}
          onClick={() => onLiveModeToggle(false)}
        >
          Replay
        </button>
        <button
          className={`mode-btn ${liveMode ? 'active' : ''}`}
          onClick={() => onLiveModeToggle(true)}
        >
          Live
        </button>
      </div>

      {!liveMode && (
        <>
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
        </>
      )}
      {liveMode && (
        <span className="header-tick-val" style={{ marginLeft: 8 }}>
          tick <strong>{currentTick}</strong>
          <span className="header-tick-max">/ {maxTick}</span>
        </span>
      )}
    </div>
  )
}
