import { ALGOS } from '../data/liveDataClient.js'
import { getBackend } from '../data/schemaCompat.js'

const STEPS = ['Recommend', 'Execute', 'Evaluate']

export default function Header({
  algo, onAlgoChange,
  currentTick, maxTick, onTickChange,
  liveMode, onLiveModeToggle,
  dataStatus,
  manifest,
  totalTraceEvents,
  snapshotsManifest,
  selectedSnapshot,
  onSelectedSnapshotChange,
  step,
  onStepChange,
}) {
  const snapshotProfiles = Array.isArray(snapshotsManifest?.profiles)
    ? snapshotsManifest.profiles : []
  const hasSnapshots = snapshotProfiles.length > 0
  const mf = manifest || {}
  // Backend source: 'xv6' | 'simulator' | 'fallback'. A demo_fallback metadata
  // flag (set by the orchestrator) downgrades the badge to FALLBACK for honesty.
  let backend = getBackend(mf)
  if (backend !== 'xv6' && mf.metadata_source === 'demo_fallback') backend = 'fallback'
  const isXv6 = backend === 'xv6'

  // Extra manifest fields (new schema with legacy fallbacks)
  const seed = mf.seed
  const workloadType = mf.workload_type || mf.workload
  const llmAlgo = mf.llm_selected_algorithm || mf.recommended_algorithm
  const executed = mf.algorithms_executed || mf.algorithms
  const executedCount = Array.isArray(executed) ? executed.length : null

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

      {/* Step navigation — Recommend / Execute / Evaluate. Visible only
          when the parent App provides step state (otherwise the live
          dashboard renders without step nav, preserving backwards
          compatibility for any caller that hasn't migrated yet). */}
      {step && typeof onStepChange === 'function' && (
        <div className="header-steps">
          {STEPS.map((s, i) => (
            <button
              key={s}
              type="button"
              className={`header-step-btn ${step === s ? 'active' : ''}`}
              onClick={() => onStepChange(s)}
              title={`Switch to ${s} screen`}
            >
              <span className="step-num">{i + 1}</span>
              {s}
            </button>
          ))}
        </div>
      )}

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

      {/* Backend source badge — the primary honesty signal (3 states) */}
      <div className={`backend-badge backend-${backend === 'xv6' ? 'xv6' : backend === 'fallback' ? 'fallback' : 'sim'}`}>
        <span className="backend-badge-text">
          {backend === 'xv6' ? 'Backend: XV6 TRACE'
            : backend === 'fallback' ? 'Backend: FALLBACK'
            : 'Backend: SIMULATOR FALLBACK'}
        </span>
        <span className="backend-badge-note">
          {backend === 'xv6' ? 'xv6 schedtest trace loaded'
            : backend === 'fallback' ? 'Demo/fallback metadata — not a real run.'
            : 'Simulator backend: for development/fallback, not real xv6 execution.'}
        </span>
      </div>

      {/* Extra manifest fields */}
      {(seed != null || workloadType || llmAlgo || executedCount != null || totalTraceEvents > 0) && (
        <div className="header-manifest-meta">
          {workloadType && (
            <span className="hm-item" title="Workload type">
              <span className="hm-label">workload</span>{workloadType}
            </span>
          )}
          {llmAlgo && (
            <span className="hm-item" title="LLM selected algorithm">
              <span className="hm-label">llm</span>{llmAlgo}
            </span>
          )}
          {executedCount != null && (
            <span
              className="hm-item"
              title={Array.isArray(executed) ? executed.join(', ') : 'Algorithms executed'}
            >
              <span className="hm-label">algos</span>{executedCount}
            </span>
          )}
          {seed != null && (
            <span className="hm-item" title="Random seed">
              <span className="hm-label">seed</span>{seed}
            </span>
          )}
          {totalTraceEvents > 0 && (
            <span className="hm-item" title="Total trace events loaded">
              <span className="hm-label">events</span>{totalTraceEvents}
            </span>
          )}
        </div>
      )}

      {/* Fallback warning banner */}
      {dataStatus.mode === 'fallback' && (
        <div className="ds-fallback-banner">
          No live data — showing fallback. Run <code>python3 scripts/orchestrator.py --backend xv6 --seed 42 --workload interactive --run-all</code>
        </div>
      )}

      <div className="header-spacer" />

      {/* Snapshot selector — visible only when snapshots_manifest.json exists.
          Default option clears the snapshot and uses the flat /live-data root. */}
      {hasSnapshots && (
        <>
          <span className="header-algo-label" title="Pre-generated xv6 profile snapshots">
            Snapshot
          </span>
          <select
            className="algo-select"
            data-demo-target="snapshot"
            value={selectedSnapshot?.profile || ''}
            onChange={e => {
              const v = e.target.value
              if (!v) { onSelectedSnapshotChange?.(null); return }
              const entry = snapshotProfiles.find(p => p.profile === v)
              if (entry) onSelectedSnapshotChange?.(entry)
            }}
            title="Switch between the default live-data and the committed xv6 profile snapshots"
          >
            <option value="">Default (current run)</option>
            {snapshotProfiles.map(p => (
              <option key={p.profile} value={p.profile}>
                {p.profile}{p.judgment ? ` · ${p.judgment}` : ''}
              </option>
            ))}
          </select>
          {selectedSnapshot && (
            <span
              className="pill"
              style={{
                background: '#ede9fe', color: '#6d28d9',
                fontSize: '0.55rem', marginLeft: 4,
              }}
              title={`Snapshot from ${selectedSnapshot.path}`}
            >
              SNAPSHOT: {selectedSnapshot.profile}
            </span>
          )}
          <div className="header-spacer" />
        </>
      )}

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
