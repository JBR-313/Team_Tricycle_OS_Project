import { useState, useMemo } from 'react'
import './App.css'

import { FIXTURES, FIXTURE_NAMES } from './data/fixtures.js'

import Header              from './components/Header.jsx'
import HeroSection         from './components/HeroSection.jsx'
import UITestControls      from './components/UITestControls.jsx'
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

export default function App() {
  // ── UI controls ──────────────────────────────────────────────
  const [preset,          setPreset]          = useState('glass')   // glass | toss | dense
  const [focusMode,       setFocusMode]       = useState('full')    // hero | full | process-flow | gantt | trace | metrics
  const [fixtureName,     setFixtureName]     = useState('interactive_heavy')
  const [maxTraceEvents,  setMaxTraceEvents]  = useState(5)
  const [showDebug,       setShowDebug]       = useState(false)

  // ── Replay ───────────────────────────────────────────────────
  const [algo, setAlgo] = useState('MLFQ')
  const [tick, setTick] = useState(30)

  // ── Derive fixture data ───────────────────────────────────────
  const fix = FIXTURES[fixtureName] || FIXTURES['interactive_heavy']
  const { traces, recommendation, guardDecision, metrics, workloadSummary, traceExplanation, ALGOS } = fix

  // Normalise algo key (traces may use 'PRIORITY' key)
  const algoKey  = ALGOS.includes(algo) ? algo : ALGOS[0]
  const traceKey = Object.keys(traces).find(k => k.toLowerCase() === algoKey.toLowerCase()) || Object.keys(traces)[0] || ''
  const events   = traces[traceKey] || []
  const maxTick  = useMemo(() => Math.max(...events.map(e => e.tick), 1), [events])

  function handleAlgoChange(newAlgo) {
    setAlgo(newAlgo)
    const newEvents = traces[Object.keys(traces).find(k => k.toLowerCase() === newAlgo.toLowerCase())] || []
    const newMax    = Math.max(...newEvents.map(e => e.tick), 1)
    setTick(Math.round(newMax * 0.55))
  }

  function handleFixtureChange(name) {
    setFixtureName(name)
    const f     = FIXTURES[name] || FIXTURES['interactive_heavy']
    const algos = f.ALGOS || []
    const first = algos[0] || 'RR'
    setAlgo(first)
    const evts  = Object.values(f.traces)[0] || []
    const mx    = Math.max(...evts.map(e => e.tick), 1)
    setTick(Math.round(mx * 0.55))
  }

  // ── Debug info ────────────────────────────────────────────────
  const debugInfo = {
    fixture:     fixtureName,
    preset,
    focusMode,
    algo:        algoKey,
    tick,
    maxTick,
    eventCount:  events.length,
    processCount: metrics?.process_count ?? '?',
    judgment:    metrics?.judgment ?? '—',
    algoKeys:    Object.keys(traces).join(', '),
  }

  // ── Shared props ──────────────────────────────────────────────
  const headerProps = {
    algo: algoKey, onAlgoChange: handleAlgoChange, ALGOS,
    currentTick: tick, maxTick, onTickChange: setTick,
    focusMode, onFocusModeChange: setFocusMode,
    fixture: fixtureName,
  }
  const utcProps = {
    preset, onPresetChange: setPreset,
    focusMode, onFocusModeChange: setFocusMode,
    fixture: fixtureName, onFixtureChange: handleFixtureChange,
    maxTraceEvents, onMaxTraceEventsChange: setMaxTraceEvents,
    showDebug, onShowDebugChange: setShowDebug,
    debugInfo,
  }

  const shellClass = `dashboard-shell preset-${preset} mode-${focusMode}`

  // ── Hero mode ─────────────────────────────────────────────────
  if (focusMode === 'hero') {
    return (
      <div className={shellClass}>
        <HeroSection
          onEnterDashboard={() => setFocusMode('full')}
          events={events}
          algo={algoKey}
          currentTick={tick}
          maxTick={maxTick}
        />
        <UITestControls {...utcProps} />
      </div>
    )
  }

  // ── Process Flow mode ─────────────────────────────────────────
  if (focusMode === 'process-flow') {
    return (
      <div className={shellClass}>
        <Header {...headerProps} />
        <div className="layout-process-flow">
          <div className="pf-main">
            <ProcessState events={events} currentTick={tick} />
          </div>
          <div className="pf-strip">
            <MainGantt events={events} currentTick={tick} maxTick={maxTick} algo={algoKey} />
            <TraceStack events={events} currentTick={tick} maxEvents={maxTraceEvents} />
          </div>
        </div>
        <UITestControls {...utcProps} />
      </div>
    )
  }

  // ── Gantt mode ────────────────────────────────────────────────
  if (focusMode === 'gantt') {
    return (
      <div className={shellClass}>
        <Header {...headerProps} />
        <div className="layout-gantt">
          <div className="gantt-main">
            <MainGantt events={events} currentTick={tick} maxTick={maxTick} algo={algoKey} large />
          </div>
          <div className="gantt-lanes">
            <ProcessLanes events={events} currentTick={tick} maxTick={maxTick} algo={algoKey} />
          </div>
          <div className="gantt-trace">
            <TraceStack events={events} currentTick={tick} maxEvents={maxTraceEvents} />
          </div>
        </div>
        <UITestControls {...utcProps} />
      </div>
    )
  }

  // ── Trace mode ────────────────────────────────────────────────
  if (focusMode === 'trace') {
    return (
      <div className={shellClass}>
        <Header {...headerProps} />
        <div className="layout-trace">
          <div className="trace-main">
            <TraceStack events={events} currentTick={tick} maxEvents={maxTraceEvents} large />
          </div>
          <div className="trace-side">
            <MainGantt events={events} currentTick={tick} maxTick={maxTick} algo={algoKey} />
            <LLMRecommendation />
            <AlgorithmGuard />
          </div>
        </div>
        <UITestControls {...utcProps} />
      </div>
    )
  }

  // ── Metrics mode ──────────────────────────────────────────────
  if (focusMode === 'metrics') {
    return (
      <div className={shellClass}>
        <Header {...headerProps} />
        <div className="layout-metrics">
          <div className="metrics-cmp">
            <AlgorithmComparison />
          </div>
          <div className="metrics-chart">
            <MetricVisualization />
          </div>
          <div className="metrics-side">
            <EvaluationResult />
            <WorkloadSummary />
          </div>
        </div>
        <UITestControls {...utcProps} />
      </div>
    )
  }

  // ── Full Dashboard (default) ──────────────────────────────────
  return (
    <div className={shellClass}>
      <Header {...headerProps} />
      <div className="dashboard-main">

        {/* ── LEFT COLUMN ── */}
        <div className="dashboard-col">
          <LLMRecommendation />
          <AlgorithmGuard />
          <EvaluationResult />
          <LLMExplanation />
        </div>

        {/* ── CENTER COLUMN ── */}
        <div className="dashboard-col">
          <MainGantt  events={events} currentTick={tick} maxTick={maxTick} algo={algoKey} />
          <ProcessState events={events} currentTick={tick} />
          <TraceStack events={events} currentTick={tick} maxEvents={maxTraceEvents} />
        </div>

        {/* ── RIGHT COLUMN ── */}
        <div className="dashboard-col">
          <ProcessLanes  events={events} currentTick={tick} maxTick={maxTick} algo={algoKey} />
          <WorkloadSummary />
          <AlgorithmComparison />
          <MetricVisualization />
        </div>
      </div>
      <UITestControls {...utcProps} />
    </div>
  )
}
