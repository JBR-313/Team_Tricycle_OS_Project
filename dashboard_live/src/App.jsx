import { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import './App.css'

import {
  ALGOS,
  loadManifest, loadRecommendation, loadGuardDecision,
  loadWorkloadSummary, loadMetrics, loadAllTraces,
  getLiveDataBase,
  loadRuntimeEvents, loadCorrectionProposal, loadCorrectionGuardDecision,
} from './data/liveDataClient.js'

// Tiny inline toolbar for the Visualization tab — algorithm + tick scrubber.
// Lives here (not Header) so the controls only appear when they're useful.
function VizToolbar({ algo, onAlgoChange, currentTick, maxTick, onTickChange }) {
  return (
    <div className="viz-toolbar">
      <label className="viz-toolbar-label">Algorithm</label>
      <select
        className="viz-toolbar-select"
        value={algo}
        onChange={e => onAlgoChange(e.target.value)}
      >
        {ALGOS.map(a => <option key={a} value={a}>{a}</option>)}
      </select>
      <label className="viz-toolbar-label">Tick</label>
      <span className="viz-toolbar-tick">{currentTick}<span className="viz-toolbar-tickmax">/ {maxTick}</span></span>
      <input
        type="range"
        className="viz-toolbar-slider"
        min={0}
        max={maxTick}
        value={currentTick}
        onChange={e => onTickChange(Number(e.target.value))}
      />
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
import CounterfactualMetricView from './components/CounterfactualMetricView.jsx'
import RuntimeCorrectionPreview from './components/RuntimeCorrectionPreview.jsx'
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
      setManifest(mf || fallbackManifest)
      setRecommendation(rec || fallbackRecommendation)
      setGuardDecision(gd || fallbackGuardDecision)
      setWorkloadSummary(wl || fallbackWorkloadSummary)
      setMetrics(mt || fallbackMetrics)
      setTraces(trResult.traces)
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

  // Default the visualization tick to a mid-trace position when the algo changes.
  useEffect(() => { setTick(Math.round(maxTick * 0.55)) }, [maxTick, algoKey])

  const totalTraceEvents = useMemo(
    () => Object.values(traces).reduce((sum, evs) => sum + (evs?.length || 0), 0),
    [traces],
  )

  function handleAlgoChange(newAlgo) {
    setAlgo(newAlgo)
    const newEvents = traces[Object.keys(traces).find(k => k.toLowerCase() === newAlgo.toLowerCase())] || []
    const newMax = Math.max(...newEvents.map(e => e.tick), 1)
    setTick(Math.round(newMax * 0.55))
  }

  const dataStatus = {
    mode: dataMode, updatedAt, manifestVersion,
    error: loadError,
  }

  // ── Tab content rendering ─────────────────────────────────────────────────
  // Page 1 = LLM **pre-execution** decision page.
  // EXACTLY three cards per dashboard_page1_pre_execution_revision_goal.md §1:
  //   - LLM RECOMMENDATION (full-width top, primary focus)
  //   - ALGORITHM GUARD   (compact, bottom-left)
  //   - LLM EXPLANATION   (large readable, bottom-right) — pre-exec only,
  //                        derived from recommendation + workloadSummary;
  //                        traceExplanation is INTENTIONALLY NOT passed here
  //                        because it is post-execution content (Page 2/3).
  function renderLLMTab() {
    return (
      <div className="page1-grid">
        <LLMRecommendation recommendation={recommendation} />
        <AlgorithmGuard    guardDecision={guardDecision} />
        <LLMExplanation
          recommendation={recommendation}
          workloadSummary={workloadSummary}
        />
      </div>
    )
  }

  function renderVisualizationTab() {
    return (
      <div className="viz-page">
        <VizToolbar
          algo={algo} onAlgoChange={handleAlgoChange}
          currentTick={tick} maxTick={maxTick} onTickChange={setTick}
        />
        <div className="tab-grid viz-grid">
          <div className="tab-col">
            <MainGantt    events={events} currentTick={tick} maxTick={maxTick} algo={algo} />
            <ProcessLanes events={events} currentTick={tick} maxTick={maxTick} algo={algo} />
          </div>
          <div className="tab-col">
            <ProcessState   events={events} currentTick={tick} />
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
          <EvaluationResult     metrics={metrics} recommendation={recommendation} />
          <AlgorithmComparison  metrics={metrics} recommendation={recommendation} selectedMetric={selectedMetric} />
        </div>
        <div className="tab-col">
          <MetricVisualization
            metrics={metrics} recommendation={recommendation}
            selectedMetric={selectedMetric}
            onSelectedMetricChange={setSelectedMetric}
          />
          <CounterfactualMetricView metrics={metrics} recommendation={recommendation} />
          <RuntimeCorrectionPreview
            runtimeEvents={runtimeEvents}
            correctionProposal={correctionProposal}
            correctionGuardDecision={correctionGuardDecision}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="dashboard-shell">
      <Header
        tab={tab} onTabChange={setTab}
        onRunComplete={loadAll}
      />
      <div className="dashboard-main tab-main">
        {tab === 'LLM' && renderLLMTab()}
        {tab === 'Visualization' && renderVisualizationTab()}
        {tab === 'Evaluation' && renderEvaluationTab()}
      </div>
    </div>
  )
}
