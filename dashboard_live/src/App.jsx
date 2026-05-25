import { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import './App.css'

import {
  ALGOS,
  loadManifest, loadRecommendation, loadGuardDecision,
  loadWorkloadSummary, loadMetrics, loadAllTraces,
} from './data/liveDataClient.js'
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

const POLL_INTERVAL_MS = 1000

function formatUpdatedAt(iso) {
  if (!iso || iso === '1970-01-01T00:00:00Z') return null
  try {
    return new Date(iso).toLocaleTimeString()
  } catch {
    return iso
  }
}

export default function App() {
  const [algo, setAlgo]         = useState('MLFQ')
  const [tick, setTick]         = useState(0)
  const [liveMode, setLiveMode] = useState(false)

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
  const [traceErrors,     setTraceErrors]     = useState({})
  const [manifestVersion, setManifestVersion] = useState(null)

  const manifestVersionRef = useRef(null)

  // ── Initial load ──────────────────────────────────────────────────────────
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
      setTraceErrors(trResult.traceErrors)
      setDataMode(usedFallback ? 'fallback' : (mf?.mode || 'simulator'))
      setUpdatedAt(mf?.updated_at ? formatUpdatedAt(mf.updated_at) : null)
      setManifestVersion(mf?.version ?? null)
      setLoadError(null)

      if (mf) manifestVersionRef.current = `${mf.version}:${mf.updated_at}`

      // Restore explanation from trace_explanation.json if available
      try {
        const exRes = await fetch('/live-data/trace_explanation.json')
        if (exRes.ok) setTraceExplanation(await exRes.json())
      } catch { /* optional file */ }

    } catch (err) {
      setLoadError(err.message)
      setDataMode('fallback')
    }
  }, [])

  useEffect(() => { loadAll() }, [loadAll])

  // ── Live polling ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!liveMode) return
    const id = setInterval(async () => {
      try {
        const mf = await loadManifest()
        const key = `${mf.version}:${mf.updated_at}`
        if (key !== manifestVersionRef.current) {
          manifestVersionRef.current = key
          await loadAll()
        }
      } catch { /* polling errors are silent */ }
    }, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [liveMode, loadAll])

  // ── Derive per-algo events ────────────────────────────────────────────────
  const algoKey  = ALGOS.includes(algo) ? algo : 'MLFQ'
  const traceKey = Object.keys(traces).find(k => k.toLowerCase() === algoKey.toLowerCase()) || 'MLFQ'
  const events   = traces[traceKey] || []
  const maxTick  = useMemo(() => Math.max(...events.map(e => e.tick), 1), [events])

  // In live mode, follow the latest tick
  useEffect(() => {
    if (liveMode) setTick(maxTick)
  }, [liveMode, maxTick])

  // Total trace event count across all loaded algorithms (for header info)
  const totalTraceEvents = useMemo(
    () => Object.values(traces).reduce((sum, evs) => sum + (evs?.length || 0), 0),
    [traces],
  )

  function handleAlgoChange(newAlgo) {
    setAlgo(newAlgo)
    const newEvents = traces[Object.keys(traces).find(k => k.toLowerCase() === newAlgo.toLowerCase())] || []
    const newMax = Math.max(...newEvents.map(e => e.tick), 1)
    setTick(liveMode ? newMax : Math.round(newMax * 0.55))
  }

  function handleLiveModeToggle(isLive) {
    setLiveMode(isLive)
    if (!isLive) setTick(Math.round(maxTick * 0.55))
    else setTick(maxTick)
  }

  const dataStatus = {
    mode:            dataMode,
    updatedAt:       updatedAt,
    manifestVersion: manifestVersion,
    error:           loadError,
    traceErrors:     traceErrors,
  }

  return (
    <div className="dashboard-shell">
      <Header
        algo={algo}
        onAlgoChange={handleAlgoChange}
        currentTick={tick}
        maxTick={maxTick}
        onTickChange={setTick}
        liveMode={liveMode}
        onLiveModeToggle={handleLiveModeToggle}
        dataStatus={dataStatus}
        manifest={manifest}
        totalTraceEvents={totalTraceEvents}
      />

      <div className="dashboard-main">
        {/* ── LEFT COLUMN ── */}
        <div className="dashboard-col">
          <LLMRecommendation  recommendation={recommendation} />
          <AlgorithmGuard     guardDecision={guardDecision} />
          <EvaluationResult   metrics={metrics} recommendation={recommendation} />
          <LLMExplanation     traceExplanation={traceExplanation} />
        </div>

        {/* ── CENTER COLUMN ── */}
        <div className="dashboard-col">
          <MainGantt    events={events} currentTick={tick} maxTick={maxTick} algo={algo} />
          <ProcessState events={events} currentTick={tick} />
          <TraceStack   events={events} currentTick={tick} />
        </div>

        {/* ── RIGHT COLUMN ── */}
        <div className="dashboard-col">
          <ProcessLanes        events={events} currentTick={tick} maxTick={maxTick} algo={algo} />
          <WorkloadSummary     workloadSummary={workloadSummary} />
          <AlgorithmComparison metrics={metrics} recommendation={recommendation} />
          <MetricVisualization metrics={metrics} recommendation={recommendation} />
        </div>
      </div>
    </div>
  )
}
