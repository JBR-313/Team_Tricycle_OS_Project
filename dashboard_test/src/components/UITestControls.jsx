import { useState } from 'react'
import { FIXTURE_NAMES } from '../data/fixtures.js'

const PRESETS = [
  { id: 'glass', label: 'Apple Glass', icon: '◈' },
  { id: 'toss',  label: 'Toss Clean',  icon: '◇' },
  { id: 'dense', label: 'Dense',        icon: '⊞' },
]

const FOCUS_MODES = [
  { id: 'hero',         label: 'Hero' },
  { id: 'full',         label: 'Full' },
  { id: 'process-flow', label: 'Process' },
  { id: 'gantt',        label: 'Gantt' },
  { id: 'trace',        label: 'Trace' },
  { id: 'metrics',      label: 'Metrics' },
]

const TRACE_EVENT_COUNTS = [3, 5, 8]

export default function UITestControls({
  preset, onPresetChange,
  focusMode, onFocusModeChange,
  fixture, onFixtureChange,
  maxTraceEvents, onMaxTraceEventsChange,
  showDebug, onShowDebugChange,
  debugInfo,
}) {
  const [open, setOpen] = useState(true)

  return (
    <div className={`utc-panel ${open ? 'utc-open' : 'utc-closed'}`}>
      <button className="utc-toggle" onClick={() => setOpen(o => !o)} title="Toggle UI test controls">
        <span className="utc-icon">{open ? '⚙' : '⚙'}</span>
        {open ? 'UI Lab' : ''}
      </button>

      {open && (
        <div className="utc-body">
          {/* Mode badge */}
          <div className="utc-lab-badge">UI TEST MODE · Static Fixture</div>

          {/* Presets */}
          <div className="utc-section">
            <div className="utc-section-label">Style Preset</div>
            <div className="utc-btn-row">
              {PRESETS.map(p => (
                <button
                  key={p.id}
                  className={`utc-preset-btn ${preset === p.id ? 'active' : ''}`}
                  onClick={() => onPresetChange(p.id)}
                  title={p.label}
                >
                  <span>{p.icon}</span>
                  <span>{p.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Focus Mode */}
          <div className="utc-section">
            <div className="utc-section-label">Focus Mode</div>
            <div className="utc-btn-row utc-btn-row-wrap">
              {FOCUS_MODES.map(m => (
                <button
                  key={m.id}
                  className={`utc-mode-btn ${focusMode === m.id ? 'active' : ''}`}
                  onClick={() => onFocusModeChange(m.id)}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>

          {/* Fixture */}
          <div className="utc-section">
            <div className="utc-section-label">Fixture</div>
            <select
              className="utc-select"
              value={fixture}
              onChange={e => onFixtureChange(e.target.value)}
            >
              {FIXTURE_NAMES.map(f => (
                <option key={f} value={f}>{f.replace(/_/g, ' ')}</option>
              ))}
            </select>
          </div>

          {/* Max Trace Events */}
          <div className="utc-section">
            <div className="utc-section-label">Max Trace Events</div>
            <div className="utc-btn-row">
              {TRACE_EVENT_COUNTS.map(n => (
                <button
                  key={n}
                  className={`utc-mode-btn ${maxTraceEvents === n ? 'active' : ''}`}
                  onClick={() => onMaxTraceEventsChange(n)}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>

          {/* Debug toggle */}
          <div className="utc-section">
            <label className="utc-toggle-label">
              <input
                type="checkbox"
                checked={showDebug}
                onChange={e => onShowDebugChange(e.target.checked)}
              />
              <span>Show Debug Info</span>
            </label>
          </div>

          {/* Debug panel */}
          {showDebug && debugInfo && (
            <div className="utc-debug">
              {Object.entries(debugInfo).map(([k, v]) => (
                <div key={k} className="utc-debug-row">
                  <span className="utc-debug-key">{k}</span>
                  <span className="utc-debug-val">{String(v)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
