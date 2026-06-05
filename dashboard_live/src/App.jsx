import { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import './App.css'

import {
  ALGOS,
  loadManifest, loadRecommendation, loadGuardDecision,
  loadWorkloadSummary, loadMetrics, loadAllTraces,
  getLiveDataBase,
  loadRuntimeEvents, loadCorrectionProposal, loadCorrectionGuardDecision,
} from './data/liveDataClient.js'
import { tickToMs, SIM_TIME_CAPTION } from './components/constants.js'

// Resolve the LLM/Guard-recommended algorithm robustly (case-insensitive),
// preferring a candidate that actually has trace events. Mirrors the goal's
// fallback order: guard decision -> recommendation -> manifest -> first
// algorithm with non-empty events -> MLFQ.
function resolveRecommendedAlgo(recommendation, guardDecision, manifest, traces) {
  const traceKey = (name) => {
    if (!name) return null
    const k = Object.keys(traces).find(
      kk => kk.toLowerCase() === String(name).toLowerCase()
    )
    return k && traces[k]?.length ? k : null
  }
  const candidates = [
    guardDecision?.scheduling_algorithm,
    guardDecision?.algorithm,
    guardDecision?.fallback_algorithm,
    recommendation?.recommended_scheduling_algorithm,
    recommendation?.algorithm,
    manifest?.llm_selected_algorithm,
    manifest?.recommended_algorithm,
  ]
  for (const c of candidates) {
    const m = traceKey(c)
    if (m) return m
  }
  const anyWithEvents = ALGOS.find(a => traceKey(a))
  return anyWithEvents || 'MLFQ'
}

// Speed labels (human-friendly) -> replay rate in trace ticks per second.
// "Instant" is special-cased: it jumps straight to the end of the trace.
export const REPLAY_SPEEDS = { Slow: 2, Normal: 6, Fast: 12, Instant: null }
const SPEED_ORDER = ['Slow', 'Normal', 'Fast', 'Instant']

// Presentation toolbar for the Visualization tab. The primary path is the
// RUN -> autoplay flow; the draggable scrubber is demoted behind a "Manual
// scrub" disclosure. All user-facing time is shown in simulated milliseconds.
function VizToolbar({
  algo, onAlgoChange, currentTick, maxTick, onTickChange,
  isPlaying, onTogglePlay, onReset, speedLabel, onSpeedChange,
  manualScrub, onToggleManual,
}) {
  const atEnd = currentTick >= maxTick
  const pct = maxTick > 0 ? Math.min(100, (currentTick / maxTick) * 100) : 0
  return (
    <div className="viz-toolbar">
      <div className="viz-toolbar-row">
        <label className="viz-toolbar-label">Algorithm</label>
        <select
          className="viz-toolbar-select"
          value={algo}
          onChange={e => onAlgoChange(e.target.value)}
        >
          {ALGOS.map(a => <option key={a} value={a}>{a}</option>)}
        </select>

        <button
          className="viz-toolbar-playbtn"
          onClick={onTogglePlay}
          title={isPlaying ? 'Pause replay' : (atEnd ? 'Replay from start' : 'Play replay')}
        >
          {isPlaying ? '⏸ Pause' : (atEnd ? '⟲ Replay' : '▶ Play')}
        </button>
        <button
          className="viz-toolbar-resetbtn"
          onClick={onReset}
          title="Reset to 0 ms"
        >
          ⏮
        </button>

        <div className="viz-toolbar-speeds" role="group" aria-label="Replay speed">
          {SPEED_ORDER.map(s => (
            <button
              key={s}
              className={`viz-toolbar-speed ${speedLabel === s ? 'active' : ''}`}
              onClick={() => onSpeedChange(s)}
              title={REPLAY_SPEEDS[s] == null
                ? 'Jump to the end immediately'
                : `${REPLAY_SPEEDS[s]} trace ticks per second`}
            >
              {s}
            </button>
          ))}
        </div>

        <div className="viz-toolbar-spacer" />

        <span className="viz-toolbar-time" title={SIM_TIME_CAPTION}>
          <span className="viz-toolbar-time-label">Replay time</span>
          <span className="viz-toolbar-time-val">{tickToMs(currentTick)} ms</span>
          <span className="viz-toolbar-time-max">/ {tickToMs(maxTick)} ms</span>
        </span>

        <button
          className={`viz-toolbar-manual ${manualScrub ? 'active' : ''}`}
          onClick={onToggleManual}
          title="Advanced: scrub replay time manually"
        >
          Manual scrub {manualScrub ? '▾' : '▸'}
        </button>
      </div>

      {/* Thin, non-draggable progress bar — the default (presentation) control. */}
      <div className="viz-progress" aria-hidden="true">
        <div className="viz-progress-fill" style={{ width: `${pct}%` }} />
      </div>

      {/* Draggable scrubber only when Manual scrub is enabled. */}
      {manualScrub && (
        <div className="viz-toolbar-row viz-manual-row">
          <label className="viz-toolbar-label">Scrub</label>
          <input
            type="range"
            className="viz-toolbar-slider"
            min={0}
            max={maxTick}
            value={currentTick}
            onChange={e => onTickChange(Number(e.target.value))}
          />
          <span className="viz-toolbar-time-val">{tickToMs(currentTick)} ms</span>
        </div>
      )}
    </div>
  )
}
import {
  fallbackManifest, fallbackRecommendation, fallbackGuardDecision,
  fallbackWorkloadSummary, fallbackMetrics, fallbackTraces,
} from './data/fallbackData.js'

import Header              from './components/Header.jsx'
import LLMRecommendation   from './components/LLMRecommendation.jsx'
import AlgorithmGuard      from './components/AlgorithmGuard.jsx'
import EvaluationResult    from './components/EvaluationResult.jsx'
import LLMExplanation      from './components/LLMExplanation.jsx'
import MainGantt           from './components/MainGantt.jsx'
import ProcessState        from './components/ProcessState.jsx'
import TraceStack          from './components/TraceStack.jsx'
import ProcessLanes        from './components/ProcessLanes.jsx'
import WorkloadSummary     from './components/WorkloadSummary.jsx'
import AlgorithmComparison from './components/AlgorithmComparison.jsx'
import MetricVisualization from './components/MetricVisualization.jsx'
// NOTE: RecommendationEvidence (WHY THIS ALGORITHM?) removed per
// dashboard_page1_pre_execution_revision_goal.md §1/§3 — its content merged
// into LLMRecommendation's description area.
// NOTE: CounterfactualMetricView ("Best Algorithm by Metric") and
// RuntimeCorrectionPreview were removed from Page 3 per the final-cleanup
// goal — runtime correction is not a working dashboard feature, only a
// talking point. The component files remain on disk for future use but
// are no longer rendered.
import MLFQQueuePanel from './components/MLFQQueuePanel.jsx'
// NOTE: RunControls / WorkloadSummary intentionally NOT rendered on Page 1
// per dashboard_page1_second_revision_goal.md §2 & §4. RUN moved into
// Header; WorkloadSummary still available for Page 2/3 use later but is
// imported by reference only.

const POLL_INTERVAL_MS = 1500

function formatUpdatedAt(iso) {
  if (!iso || iso === '1970-01-01T00:00:00Z') return null
  try { return new Date(iso).toLocaleTimeString() } catch { return iso }
}

export default function App() {
  // ── Tab state (LLM | Visualization | Evaluation) ─────────────────────────
  const [tab, setTab]   = useState('LLM')
  const [algo, setAlgo] = useState('MLFQ')
  const [tick, setTick] = useState(0)
  const [selectedMetric, setSelectedMetric] = useState('avg_response_time')
  const [isPlaying, setIsPlaying] = useState(false)
  const [speedLabel, setSpeedLabel] = useState('Normal')  // Slow | Normal | Fast | Instant
  const [manualScrub, setManualScrub] = useState(false)

  const [traces,          setTraces]          = useState(fallbackTraces)
  const [recommendation,  setRecommendation]  = useState(null)
  const [guardDecision,   setGuardDecision]   = useState(null)
  const [workloadSummary, setWorkloadSummary] = useState(null)
  const [metrics,         setMetrics]         = useState(null)
  const [traceExplanation,setTraceExplanation]= useState(null)
  const [manifest,        setManifest]        = useState(null)
  const [dataMode,        setDataMode]        = useState('loading')
  const [updatedAt,       setUpdatedAt]       = useState(null)
  const [loadError,       setLoadError]       = useState(null)
  const [manifestVersion, setManifestVersion] = useState(null)
  const [runtimeEvents,           setRuntimeEvents]           = useState(null)
  const [correctionProposal,      setCorrectionProposal]      = useState(null)
  const [correctionGuardDecision, setCorrectionGuardDecision] = useState(null)

  const manifestVersionRef = useRef(null)
  const recommendedAlgoRef = useRef('MLFQ')
  const algoInitializedRef = useRef(false)

  const loadAll = useCallback(async () => {
    try {
      const [mf, rec, gd, wl, mt, trResult] = await Promise.all([
        loadManifest().catch(() => null),
        loadRecommendation().catch(() => null),
        loadGuardDecision().catch(() => null),
        loadWorkloadSummary().catch(() => null),
        loadMetrics().catch(() => null),
        loadAllTraces(),
      ])
      const usedFallback = !mf
      const mfEff = mf || fallbackManifest
      const recEff = rec || fallbackRecommendation
      const gdEff = gd || fallbackGuardDecision
      setManifest(mfEff)
      setRecommendation(recEff)
      setGuardDecision(gdEff)
      setWorkloadSummary(wl || fallbackWorkloadSummary)
      setMetrics(mt || fallbackMetrics)
      setTraces(trResult.traces)

      // Resolve the recommended algorithm from the freshly loaded data and
      // remember it so RUN-complete can reset the replay to it. On the very
      // first load, also default the visualization to it (instead of the
      // hardcoded 'MLFQ') unless the user has already picked one.
      const recommended = resolveRecommendedAlgo(recEff, gdEff, mfEff, trResult.traces)
      recommendedAlgoRef.current = recommended
      if (!algoInitializedRef.current) {
        algoInitializedRef.current = true
        setAlgo(recommended)
      }
      setDataMode(usedFallback ? 'fallback' : (mf?.mode || 'simulator'))
      setUpdatedAt(mf?.updated_at ? formatUpdatedAt(mf.updated_at) : null)
      setManifestVersion(mf?.version ?? null)
      setLoadError(null)
      if (mf) manifestVersionRef.current = `${mf.version}:${mf.updated_at}`

      try {
        const exRes = await fetch(`${getLiveDataBase()}/trace_explanation.json`)
        if (exRes.ok) setTraceExplanation(await exRes.json())
      } catch {/* optional */}

      const [re, cp, cd] = await Promise.all([
        loadRuntimeEvents(),
        loadCorrectionProposal(),
        loadCorrectionGuardDecision(),
      ])
      setRuntimeEvents(re)
      setCorrectionProposal(cp)
      setCorrectionGuardDecision(cd)
    } catch (err) {
      setLoadError(err.message)
      setDataMode('fallback')
    }
  }, [])

  useEffect(() => { loadAll() }, [loadAll])

  // Lightweight always-on poll (no Live toggle anymore — RUN button drives changes).
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const mf = await loadManifest()
        const key = `${mf.version}:${mf.updated_at}`
        if (key !== manifestVersionRef.current) {
          manifestVersionRef.current = key
          await loadAll()
        }
      } catch { /* silent */ }
    }, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [loadAll])

  // ── Derive per-algo events ────────────────────────────────────────────────
  const algoKey  = ALGOS.includes(algo) ? algo : 'MLFQ'
  const traceKey = Object.keys(traces).find(k => k.toLowerCase() === algoKey.toLowerCase()) || 'MLFQ'
  const events   = traces[traceKey] || []
  const maxTick  = useMemo(() => Math.max(...events.map(e => e.tick), 1), [events])

  // Pseudo-live replay: while isPlaying, advance simulated time one trace tick
  // per interval at the selected speed (trace ticks per second). Stops at the
  // end of the trace (no looping — feels like a real run completing).
  useEffect(() => {
    if (!isPlaying) return
    const ticksPerSec = REPLAY_SPEEDS[speedLabel]
    if (!ticksPerSec) return  // 'Instant' is handled in handleSpeedChange
    const intervalMs = Math.max(16, Math.round(1000 / ticksPerSec))
    const id = setInterval(() => {
      setTick(t => {
        if (t >= maxTick) { setIsPlaying(false); return t }
        return t + 1
      })
    }, intervalMs)
    return () => clearInterval(id)
  }, [isPlaying, speedLabel, maxTick])

  const totalTraceEvents = useMemo(
    () => Object.values(traces).reduce((sum, evs) => sum + (evs?.length || 0), 0),
    [traces],
  )

  // Manual algorithm change: reset replay to the start and pause, so the user
  // can re-watch this algorithm from 0 ms with the play button.
  function handleAlgoChange(newAlgo) {
    setAlgo(newAlgo)
    setIsPlaying(false)
    setTick(0)
  }

  function handleSpeedChange(label) {
    if (label === 'Instant') {
      // Jump straight to the end of the trace.
      setIsPlaying(false)
      setTick(maxTick)
      return
    }
    setSpeedLabel(label)
    // Choosing a play speed starts/continues playback (unless already at end).
    setIsPlaying(p => (p ? p : tick < maxTick))
  }

  // Manual scrub: pause auto-play so user controls take over.
  function handleTickChange(newTick) {
    setIsPlaying(false)
    setTick(newTick)
  }

  function handleTogglePlay() {
    setIsPlaying(p => {
      if (!p && tick >= maxTick) setTick(0)  // at end → replay from start
      return !p
    })
  }

  function handleReset() {
    setIsPlaying(false)
    setTick(0)
  }

  // After a RUN completes (new traces arrive): switch to the Visualization tab,
  // select the LLM/Guard-recommended algorithm, reset replay time to 0, and
  // auto-play so the user watches the scheduler execution unfold from the start.
  const onRunComplete = useCallback(() => {
    loadAll().then(() => {
      setTab('Visualization')
      setAlgo(recommendedAlgoRef.current)
      setTick(0)
      setSpeedLabel('Normal')
      setIsPlaying(true)
    })
  }, [loadAll])

  const dataStatus = {
    mode: dataMode, updatedAt, manifestVersion,
    error: loadError,
  }

  // ── Tab content rendering ─────────────────────────────────────────────────
  // Page 1 = LLM **pre-execution** decision page.
  // Two-column layout: left column stacks LLM RECOMMENDATION (top) +
  // ALGORITHM GUARD (bottom); right column holds LLM EXPLANATION at full
  // card height. traceExplanation is INTENTIONALLY NOT passed here because
  // it is post-execution content (Page 2/3).
  function renderLLMTab() {
    return (
      <div className="page1-layout">
        <div className="page1-left">
          <LLMRecommendation recommendation={recommendation} />
          <AlgorithmGuard    guardDecision={guardDecision} />
        </div>
        <div className="page1-right">
          <LLMExplanation
            recommendation={recommendation}
            workloadSummary={workloadSummary}
          />
        </div>
      </div>
    )
  }

  function renderVisualizationTab() {
    const backendLabel = dataMode === 'xv6-log' || dataMode === 'xv6'
      ? 'actual xv6 scheduler trace'
      : dataMode === 'fallback'
        ? 'bundled sample trace'
        : 'actual scheduler trace'
    return (
      <div className="viz-page">
        <div className="viz-replay-status" title={SIM_TIME_CAPTION}>
          <span className="viz-replay-dot" />
          <span className="viz-replay-text">
            Pseudo-live replay · {backendLabel} · simulated time
          </span>
          <span className="viz-replay-sub">
            Replaying the already-generated trace with time dilation — not live kernel control.
          </span>
        </div>
        <VizToolbar
          algo={algo} onAlgoChange={handleAlgoChange}
          currentTick={tick} maxTick={maxTick} onTickChange={handleTickChange}
          isPlaying={isPlaying} onTogglePlay={handleTogglePlay}
          onReset={handleReset}
          speedLabel={speedLabel} onSpeedChange={handleSpeedChange}
          manualScrub={manualScrub} onToggleManual={() => setManualScrub(m => !m)}
        />
        <div className="tab-grid viz-grid">
          <div className="tab-col viz-col-left">
            <MainGantt    events={events} currentTick={tick} maxTick={maxTick} algo={algo} />
            <ProcessState events={events} currentTick={tick} />
          </div>
          <div className="tab-col viz-col-right">
            <ProcessLanes   events={events} currentTick={tick} maxTick={maxTick} algo={algo} />
            <MLFQQueuePanel events={events} currentTick={tick} algo={algo} />
            <TraceStack     events={events} currentTick={tick} />
          </div>
        </div>
      </div>
    )
  }

  function renderEvaluationTab() {
    return (
      <div className="tab-grid eval-grid">
        <div className="tab-col">
          <EvaluationResult    metrics={metrics} recommendation={recommendation} />
          <AlgorithmComparison metrics={metrics} recommendation={recommendation} selectedMetric={selectedMetric} />
        </div>
        <div className="tab-col">
          <MetricVisualization
            metrics={metrics} recommendation={recommendation}
            selectedMetric={selectedMetric}
            onSelectedMetricChange={setSelectedMetric}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="dashboard-shell">
      <Header
        tab={tab} onTabChange={setTab}
        onRunComplete={onRunComplete}
      />
      <div className="dashboard-main tab-main">
        {tab === 'LLM' && renderLLMTab()}
        {tab === 'Visualization' && renderVisualizationTab()}
        {tab === 'Evaluation' && renderEvaluationTab()}
      </div>
    </div>
  )
}
