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
import Card                from './components/Card.jsx'
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

const STEPS = ['Recommend', 'Execute', 'Evaluate']

const STATE_DOT = {
  Running:    '#2563eb',
  Ready:      '#7c3aed',
  Waiting:    '#d97706',
  Terminated: '#64748b',
}

// Inline "Running Now" info card for the Execute screen (live stats from trace).
function ExecuteInfoCard({ events, tick, algo }) {
  const stats = useMemo(() => {
    const visible = events.filter(e => e.tick <= tick)
    const state = {}
    let preemptions = 0
    for (const ev of visible) {
      if (ev.event === 'PREEMPT') preemptions++
      if (ev.pid < 0) continue
      if (['ARRIVE', 'PREEMPT', 'WAKEUP'].includes(ev.event)) state[ev.pid] = 'Ready'
      else if (ev.event === 'DISPATCH') state[ev.pid] = 'Running'
      else if (ev.event === 'SLEEP')    state[ev.pid] = 'Waiting'
      else if (ev.event === 'EXIT')     state[ev.pid] = 'Terminated'
    }
    const counts = { Running: 0, Ready: 0, Waiting: 0, Terminated: 0 }
    for (const s of Object.values(state)) counts[s]++
    const running = Object.entries(state).find(([, s]) => s === 'Running')?.[0] ?? null
    const totalProcs = new Set(events.filter(e => e.pid > 0).map(e => e.pid)).size
    return { counts, running, totalProcs, done: counts.Terminated, preemptions }
  }, [events, tick])

  const { counts, running, totalProcs, done, preemptions } = stats
  const pct = totalProcs ? Math.round((done / totalProcs) * 100) : 0

  return (
    <Card className="exec-info-card">
      <div className="card-label">Running Now</div>
      <div className="exec-info-pid" style={{ color: running ? 'var(--accent)' : 'var(--text-3)' }}>
        {running ? `P${running}` : '—'}
      </div>
      <div className="exec-info-sub">Tick {tick} · {algo}</div>
      <hr className="divider" />
      <div className="exec-stat-block">
        <div className="exec-stat-head">
          <span>Progress</span>
          <span className="exec-stat-strong">{done}/{totalProcs}</span>
        </div>
        <div className="exec-progress-track">
          <div className="exec-progress-fill" style={{ width: `${pct}%` }} />
        </div>
      </div>
      <div className="exec-stat-block">
        <div className="exec-stat-head"><span>State</span></div>
        {['Running', 'Ready', 'Waiting', 'Terminated'].map(s => (
          <div key={s} className="exec-state-row">
            <span className="exec-state-dot" style={{ background: STATE_DOT[s] }} />
            <span className="exec-state-name">{s === 'Terminated' ? 'Done' : s}</span>
            <span className="exec-state-count">{counts[s]}</span>
          </div>
        ))}
      </div>
      <div className="exec-stat-block">
        <div className="exec-state-row">
          <span className="exec-state-name">Preemptions</span>
          <span className="exec-state-count">{preemptions}</span>
        </div>
      </div>
      <div className="exec-info-foot">Source: <strong>trace</strong></div>
    </Card>
  )
}

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
  const [selectedMetric, setSelectedMetric] = useState('avg_response_time')
  const [step, setStep] = useState('Recommend')
  const [debugOpen, setDebugOpen] = useState(false)

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

  // On first data load (replay mode), jump to a mid-run tick so the Execute
  // screen shows activity instead of an empty tick=0 view.
  const didInitTick = useRef(false)
  useEffect(() => {
    if (!didInitTick.current && !liveMode && maxTick > 1) {
      didInitTick.current = true
      setTick(Math.round(maxTick * 0.55))
    }
  }, [maxTick, liveMode])

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

      <div className="dashboard-steps-wrap">
        {/* Step navigation */}
        <div className="step-nav">
          {STEPS.map((s, i) => (
            <button
              key={s}
              className={`header-step-btn ${step === s ? 'active' : ''}`}
              onClick={() => setStep(s)}
            >
              <span className="step-num">{i + 1}</span>{s}
            </button>
          ))}
        </div>

        {/* ── SCREEN 1: RECOMMEND ── */}
        {step === 'Recommend' && (
          <div className="screen-recommend">
            <div className="rec-top">
              <WorkloadSummary workloadSummary={workloadSummary} />
            </div>
            <div className="rec-left">
              <LLMRecommendation recommendation={recommendation} metrics={metrics} />
            </div>
            <div className="rec-right">
              <AlgorithmGuard guardDecision={guardDecision} />
              <LLMExplanation traceExplanation={traceExplanation} />
            </div>
          </div>
        )}

        {/* ── SCREEN 2: EXECUTE ── */}
        {step === 'Execute' && (
          <div className="screen-execute">
            <div className="exec-gantt">
              <MainGantt events={events} currentTick={tick} maxTick={maxTick} algo={algo} />
            </div>
            <div className="exec-bottom">
              <ExecuteInfoCard events={events} tick={tick} algo={algo} />
              <ProcessState events={events} currentTick={tick} />
              <ProcessLanes events={events} currentTick={tick} maxTick={maxTick} algo={algo} />
            </div>
            <div className={`exec-debug card ${debugOpen ? 'exec-debug-open' : ''}`}>
              <button className="exec-debug-toggle" onClick={() => setDebugOpen(o => !o)}>
                <span>{debugOpen ? '▾' : '▸'}</span>
                Debug Trace Events
                <span className="exec-debug-count">
                  {events.filter(e => e.tick <= tick).length} events @ tick {tick}
                </span>
              </button>
              {debugOpen && (
                <div className="exec-debug-body">
                  <TraceStack events={events} currentTick={tick} />
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── SCREEN 3: EVALUATE ── */}
        {step === 'Evaluate' && (
          <div className="screen-evaluate">
            <div className="eval-top">
              <EvaluationResult metrics={metrics} recommendation={recommendation} />
              <LLMExplanation traceExplanation={traceExplanation} />
            </div>
            <div className="eval-bottom">
              <MetricVisualization metrics={metrics} recommendation={recommendation} selectedMetric={selectedMetric} onSelectedMetricChange={setSelectedMetric} />
              <AlgorithmComparison metrics={metrics} recommendation={recommendation} selectedMetric={selectedMetric} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
