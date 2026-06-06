import { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import './App.css'

import {
  ALGOS,
  loadManifest, loadRecommendation, loadGuardDecision,
  loadWorkloadSummary, loadMetrics, loadAllTraces,
  getLiveDataBase,
  loadRuntimeEvents, loadCorrectionProposal, loadCorrectionGuardDecision, loadCorrectionApplied,
  loadBurstAblation,
} from './data/liveDataClient.js'
import { tickToMs } from './components/constants.js'
import { useRun } from './data/useRun.js'

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

// ── Staged-demo phase machine ────────────────────────────────────────────────
// Drives the RUN button behaviour and the LLM-tab reveal. The dashboard opens
// idle; the first RUN reveals the LLM analysis like a chatbot answer; the
// second RUN starts the (frontend-only) visualization replay; once the replay
// finishes the same button offers to jump to Evaluation.
const DemoPhase = {
  IDLE:               'idle',
  ANALYZING_LLM:      'analyzing_llm',
  READY_TO_VISUALIZE: 'ready_to_visualize',
  VISUALIZING:        'visualizing',
  REPLAY_DONE:        'replay_done',
}

const RUN_LABEL = {
  [DemoPhase.IDLE]:               'RUN ANALYSIS',
  [DemoPhase.ANALYZING_LLM]:      'ANALYZING…',
  [DemoPhase.READY_TO_VISUALIZE]: 'RUN VISUALIZATION',
  [DemoPhase.VISUALIZING]:        'REPLAYING…',
  [DemoPhase.REPLAY_DONE]:        'VIEW EVALUATION',
}

// Presentation-friendly replay speeds, expressed as milliseconds of wall-clock
// time per trace tick. Default is "Slow" — slow enough to follow process-state
// transitions on a projector. The goal is readability, not physical accuracy.
export const REPLAY_SPEEDS = {
  'Super Slow': 500,
  'Slow':       175,
  'Real Time':  40,
}
const SPEED_ORDER = ['Super Slow', 'Slow', 'Real Time']

// Reveal timeline (ms from the start of the reveal). Each step advances one
// reveal stage; LLM cards render placeholder -> typing -> done based on it.
//   stage 1: analysis status messages
//   stage 2: recommendation (typewriter)
//   stage 3: algorithm guard
//   stage 4: explanation (typewriter)
//   stage 5: done -> READY_TO_VISUALIZE
const REVEAL_SCHEDULE = [
  { stage: 1, delay: 0 },
  { stage: 2, delay: 2600 },
  { stage: 3, delay: 5400 },
  { stage: 4, delay: 6600 },
  { stage: 5, delay: 9600 },
]

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
          title="Restart from 0 ms"
        >
          ⏮
        </button>

        <div className="viz-toolbar-speeds" role="group" aria-label="Replay speed">
          {SPEED_ORDER.map(s => (
            <button
              key={s}
              className={`viz-toolbar-speed ${speedLabel === s ? 'active' : ''}`}
              onClick={() => onSpeedChange(s)}
              title={`${REPLAY_SPEEDS[s]} ms per step`}
            >
              {s}
            </button>
          ))}
        </div>

        <div className="viz-toolbar-spacer" />

        <span className="viz-toolbar-time">
          <span className="viz-toolbar-time-label">Elapsed</span>
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
import TraceExplanationCard from './components/TraceExplanationCard.jsx'
import RuntimeCorrectionCard from './components/RuntimeCorrectionCard.jsx'
import LLMExplanation      from './components/LLMExplanation.jsx'
import AnalyzingStatus     from './components/AnalyzingStatus.jsx'
import MainGantt           from './components/MainGantt.jsx'
import ProcessState        from './components/ProcessState.jsx'
import TraceStack          from './components/TraceStack.jsx'
import ProcessLanes        from './components/ProcessLanes.jsx'
import AlgorithmComparison from './components/AlgorithmComparison.jsx'
import MetricVisualization from './components/MetricVisualization.jsx'
import MLFQQueuePanel      from './components/MLFQQueuePanel.jsx'
import LLMContributionCard from './components/LLMContributionCard.jsx'

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
  const [speedLabel, setSpeedLabel] = useState('Slow')  // Super Slow | Slow | Real Time
  const [manualScrub, setManualScrub] = useState(false)

  // ── Staged-demo state ────────────────────────────────────────────────────
  const [demoPhase,   setDemoPhase]   = useState(DemoPhase.IDLE)
  const [revealStage, setRevealStage] = useState(0)
  const revealTimersRef = useRef([])
  // True only between a user-initiated backend RUN and its completion, so the
  // reveal fires for a real click and NOT for the spurious DONE that useRun
  // detects on mount when a previous run is already finished (keeps the LLM
  // tab idle until the user presses RUN — goal §1).
  const runInitiatedRef = useRef(false)

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
  const [correctionApplied,       setCorrectionApplied]       = useState(null)
  const [burstAblation,           setBurstAblation]           = useState(null)

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

      const [re, cp, cd, ca, ab] = await Promise.all([
        loadRuntimeEvents(),
        loadCorrectionProposal(),
        loadCorrectionGuardDecision(),
        loadCorrectionApplied(),
        loadBurstAblation(),
      ])
      setRuntimeEvents(re)
      setCorrectionProposal(cp)
      setCorrectionGuardDecision(cd)
      setCorrectionApplied(ca)
      setBurstAblation(ab)
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
  // per interval at the selected speed (ms per tick). Stops at the end of the
  // trace (no looping — feels like a real run completing).
  useEffect(() => {
    if (!isPlaying) return
    const intervalMs = REPLAY_SPEEDS[speedLabel] || REPLAY_SPEEDS['Slow']
    const id = setInterval(() => {
      setTick(t => {
        if (t >= maxTick) { setIsPlaying(false); return t }
        return t + 1
      })
    }, intervalMs)
    return () => clearInterval(id)
  }, [isPlaying, speedLabel, maxTick])

  // When an autoplay replay reaches the end, advance the demo phase so the RUN
  // button becomes "VIEW EVALUATION". We do NOT auto-switch tabs — the
  // presenter may want to keep explaining the finished visualization.
  useEffect(() => {
    if (demoPhase === DemoPhase.VISUALIZING && maxTick > 0 && tick >= maxTick) {
      setDemoPhase(DemoPhase.REPLAY_DONE)
    }
  }, [tick, maxTick, demoPhase])

  // ── Reveal sequence ───────────────────────────────────────────────────────
  const clearRevealTimers = useCallback(() => {
    revealTimersRef.current.forEach(clearTimeout)
    revealTimersRef.current = []
  }, [])

  const startReveal = useCallback(() => {
    clearRevealTimers()
    setDemoPhase(DemoPhase.ANALYZING_LLM)
    setRevealStage(0)
    setTab('LLM')
    REVEAL_SCHEDULE.forEach(({ stage, delay }) => {
      const id = setTimeout(() => {
        setRevealStage(stage)
        if (stage >= 5) setDemoPhase(DemoPhase.READY_TO_VISUALIZE)
      }, delay)
      revealTimersRef.current.push(id)
    })
  }, [clearRevealTimers])

  useEffect(() => () => clearRevealTimers(), [clearRevealTimers])

  // ── Run pipeline (lifted here so the header RUN button is phase-aware) ──────
  // When the backend run completes, refresh data and start the LLM reveal.
  const onBackendComplete = useCallback(() => {
    loadAll().then(() => {
      if (runInitiatedRef.current) {
        runInitiatedRef.current = false
        startReveal()
      }
    })
  }, [loadAll, startReveal])

  const { available: runAvailable, state: runState, inFlight: runInFlight, startRun } =
    useRun(onBackendComplete)

  // If the backend run errors while we are waiting, fall back to revealing the
  // already-loaded (or fallback) data so the demo never gets stuck.
  useEffect(() => {
    if (demoPhase === DemoPhase.ANALYZING_LLM && runState === 'ERROR') {
      // Reset the run guard so a subsequent RUN click is not ignored, then
      // reveal the already-loaded (or fallback) analysis so we never get stuck.
      runInitiatedRef.current = false
      startReveal()
    }
  }, [demoPhase, runState, startReveal])

  function startVisualization() {
    setTab('Visualization')
    setAlgo(recommendedAlgoRef.current)
    setTick(0)
    setSpeedLabel('Slow')
    setManualScrub(false)
    setDemoPhase(DemoPhase.VISUALIZING)
    setIsPlaying(true)
  }

  // Phase-aware primary action for the header RUN button.
  const handlePrimaryRun = useCallback(() => {
    if (demoPhase === DemoPhase.IDLE) {
      if (runAvailable) {
        // Kick off the real backend run; reveal starts on completion.
        runInitiatedRef.current = true
        startRun()
        setDemoPhase(DemoPhase.ANALYZING_LLM)
        setRevealStage(0)
      } else {
        // Run-server offline → reveal the bundled/fallback analysis directly.
        startReveal()
      }
    } else if (demoPhase === DemoPhase.READY_TO_VISUALIZE) {
      startVisualization()
    } else if (demoPhase === DemoPhase.REPLAY_DONE) {
      setTab('Evaluation')
    }
    // ANALYZING_LLM / VISUALIZING: button disabled, nothing to do.
  }, [demoPhase, runAvailable, startRun, startReveal])

  const runDisabled =
    demoPhase === DemoPhase.ANALYZING_LLM ||
    demoPhase === DemoPhase.VISUALIZING ||
    (demoPhase === DemoPhase.IDLE && runAvailable === null)

  const runLabel = RUN_LABEL[demoPhase] || 'RUN'

  // Pill text mirrors the backend run state while it is meaningful; otherwise
  // it reflects the demo phase.
  const runPill =
    demoPhase === DemoPhase.ANALYZING_LLM ? (runInFlight ? runState : 'ANALYZING')
    : demoPhase === DemoPhase.VISUALIZING ? 'REPLAYING'
    : demoPhase === DemoPhase.READY_TO_VISUALIZE ? 'READY'
    : demoPhase === DemoPhase.REPLAY_DONE ? 'DONE'
    : 'IDLE'

  // ── Visualization controls ────────────────────────────────────────────────
  // Manual algorithm change: reset replay to the start and pause.
  function handleAlgoChange(newAlgo) {
    setAlgo(newAlgo)
    setIsPlaying(false)
    setTick(0)
  }

  function handleSpeedChange(label) {
    setSpeedLabel(label)
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

  // ── Tab content rendering ─────────────────────────────────────────────────
  // Page 1 = LLM pre-execution decision page. Staged reveal: idle hero until
  // the first RUN, then placeholder -> typewriter -> completed content.
  function renderLLMTab() {
    if (demoPhase === DemoPhase.IDLE) {
      return (
        <div className="llm-idle-layout">
          <div className="llm-idle-hero">
            <h2 className="llm-idle-title">Ready to analyze workload</h2>
            <p className="llm-idle-sub">
              Press <strong>RUN ANALYSIS</strong> to let the LLM read the workload
              and recommend a scheduling algorithm.
            </p>
            <div className="llm-idle-steps">
              <span className="llm-idle-step">1 · Analyze workload</span>
              <span className="llm-idle-step">2 · Recommend algorithm</span>
              <span className="llm-idle-step">3 · Validate &amp; explain</span>
            </div>
          </div>
        </div>
      )
    }

    const showRec   = revealStage >= 2
    const typingRec = revealStage === 2
    const showGuard = revealStage >= 3
    const showExpl  = revealStage >= 4
    const typingExpl = revealStage === 4
    const analyzing = revealStage <= 1

    return (
      <div className="page1-layout">
        <div className="page1-left">
          <AnalyzingStatus active={analyzing} />
          <LLMRecommendation recommendation={recommendation} show={showRec} typing={typingRec} />
          <AlgorithmGuard    guardDecision={guardDecision} show={showGuard} />
        </div>
        <div className="page1-right">
          <LLMExplanation
            recommendation={recommendation}
            workloadSummary={workloadSummary}
            show={showExpl}
            typing={typingExpl}
          />
        </div>
      </div>
    )
  }

  function renderVisualizationTab() {
    return (
      <div className="viz-page">
        <VizToolbar
          algo={algo} onAlgoChange={handleAlgoChange}
          currentTick={tick} maxTick={maxTick} onTickChange={handleTickChange}
          isPlaying={isPlaying} onTogglePlay={handleTogglePlay}
          onReset={handleReset}
          speedLabel={speedLabel} onSpeedChange={handleSpeedChange}
          manualScrub={manualScrub} onToggleManual={() => setManualScrub(m => !m)}
        />
        <div className={`tab-grid viz-grid ${algo === 'MLFQ' ? 'viz-grid-mlfq' : ''}`}>
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
          <TraceExplanationCard explanation={traceExplanation} />
          <RuntimeCorrectionCard correction={correctionApplied} />
          <LLMContributionCard ablation={burstAblation} />
        </div>
      </div>
    )
  }

  return (
    <div className="dashboard-shell">
      <Header
        tab={tab} onTabChange={setTab}
        runAvailable={runAvailable}
        runLabel={runLabel}
        runDisabled={runDisabled}
        runPill={runPill}
        onRunClick={handlePrimaryRun}
        minimal={demoPhase === DemoPhase.IDLE}
        manifest={manifest}
        loadError={!!loadError}
      />
      <div className="dashboard-main tab-main">
        {tab === 'LLM' && renderLLMTab()}
        {tab === 'Visualization' && renderVisualizationTab()}
        {tab === 'Evaluation' && renderEvaluationTab()}
      </div>
    </div>
  )
}
