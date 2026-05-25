import { useState, useMemo } from 'react'
import './App.css'

import { FIXTURES, FIXTURE_NAMES } from './data/fixtures.js'

import Header              from './components/Header.jsx'
import Card                from './components/Card.jsx'
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

// ── Inline execute info card ───────────────────────────────
const STATE_DOT = {
  Running:    '#2563eb',
  Ready:      '#7c3aed',
  Waiting:    '#d97706',
  Terminated: '#64748b',
}

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
    const corrections = visible.filter(e => e.event === 'CORRECTION_APPLIED').length
    return { counts, running, totalProcs, done: counts.Terminated, preemptions, corrections }
  }, [events, tick])

  const { counts, running, totalProcs, done, preemptions, corrections } = stats
  const pct = totalProcs ? Math.round((done / totalProcs) * 100) : 0

  return (
    <Card className="exec-info-card">
      <div className="card-label">Running Now</div>
      <div className="exec-info-pid" style={{ color: running ? 'var(--accent)' : 'var(--text-3)' }}>
        {running ? `P${running}` : '—'}
      </div>
      <div className="exec-info-sub">Tick {tick} · {algo}</div>

      <hr className="divider" />

      {/* Completion progress */}
      <div className="exec-stat-block">
        <div className="exec-stat-head">
          <span>Progress</span>
          <span className="exec-stat-strong">{done}/{totalProcs}</span>
        </div>
        <div className="exec-progress-track">
          <div className="exec-progress-fill" style={{ width: `${pct}%` }} />
        </div>
      </div>

      {/* Live state breakdown */}
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

      {/* Counters */}
      <div className="exec-stat-block">
        <div className="exec-state-row">
          <span className="exec-state-name">Preemptions</span>
          <span className="exec-state-count">{preemptions}</span>
        </div>
        {corrections > 0 && (
          <div className="exec-state-row" style={{ color: '#b45309' }}>
            <span className="exec-state-name">⚡ Corrections</span>
            <span className="exec-state-count">{corrections}</span>
          </div>
        )}
      </div>

      <div className="exec-info-foot">Source: <strong>fixture</strong></div>
    </Card>
  )
}

export default function App() {
  // ── UI controls ──────────────────────────────────────────────
  const [preset,         setPreset]         = useState('glass')
  const [focusMode,      setFocusMode]      = useState('full')
  const [fixtureName,    setFixtureName]    = useState('interactive_heavy')
  const [maxTraceEvents, setMaxTraceEvents] = useState(5)
  const [showDebug,      setShowDebug]      = useState(false)
  const [debugOpen,      setDebugOpen]      = useState(false)

  // ── Step navigation ──────────────────────────────────────────
  const [step, setStep] = useState('Recommend')

  // ── Replay ───────────────────────────────────────────────────
  const [algo, setAlgo] = useState('MLFQ')
  const [tick, setTick] = useState(30)

  // ── Derive fixture data ───────────────────────────────────────
  const fix = FIXTURES[fixtureName] || FIXTURES['interactive_heavy']
  const { traces, ALGOS } = fix

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
    fixture:      fixtureName,
    preset,
    focusMode,
    step,
    algo:         algoKey,
    tick,
    maxTick,
    eventCount:   events.length,
    algoKeys:     Object.keys(traces).join(', '),
  }

  // ── Shared props ──────────────────────────────────────────────
  const headerProps = {
    algo: algoKey, onAlgoChange: handleAlgoChange, ALGOS,
    currentTick: tick, maxTick, onTickChange: setTick,
    step, onStepChange: setStep,
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

  // ── Dev override: Hero ────────────────────────────────────────
  if (focusMode === 'hero') {
    return (
      <div className={shellClass}>
        <HeroSection
          onEnterDashboard={() => setFocusMode('full')}
          events={events} algo={algoKey} currentTick={tick} maxTick={maxTick}
        />
        <UITestControls {...utcProps} />
      </div>
    )
  }

  // ── Dev override: Process Flow ────────────────────────────────
  if (focusMode === 'process-flow') {
    return (
      <div className={shellClass}>
        <Header {...headerProps} />
        <div className="layout-process-flow">
          <div className="pf-main"><ProcessState events={events} currentTick={tick} /></div>
          <div className="pf-strip">
            <MainGantt events={events} currentTick={tick} maxTick={maxTick} algo={algoKey} />
            <TraceStack events={events} currentTick={tick} maxEvents={maxTraceEvents} />
          </div>
        </div>
        <UITestControls {...utcProps} />
      </div>
    )
  }

  // ── Dev override: Gantt ───────────────────────────────────────
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

  // ── Dev override: Trace ───────────────────────────────────────
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

  // ── Dev override: Metrics ─────────────────────────────────────
  if (focusMode === 'metrics') {
    return (
      <div className={shellClass}>
        <Header {...headerProps} />
        <div className="layout-metrics">
          <div className="metrics-cmp"><AlgorithmComparison /></div>
          <div className="metrics-chart"><MetricVisualization /></div>
          <div className="metrics-side">
            <EvaluationResult />
            <WorkloadSummary />
          </div>
        </div>
        <UITestControls {...utcProps} />
      </div>
    )
  }

  // ── Step-based Dashboard (default: full) ──────────────────────
  return (
    <div className={shellClass}>
      <Header {...headerProps} />

      {/* ── SCREEN 1: RECOMMEND ─────────────────────────────── */}
      {step === 'Recommend' && (
        <div className="screen-recommend">
          {/* Top banner: Workload Summary (full width) */}
          <div className="rec-top">
            <WorkloadSummary />
          </div>

          {/* Left: LLM Recommendation (dominant) */}
          <div className="rec-left">
            <LLMRecommendation />
          </div>

          {/* Right: Guard + short LLM reasoning */}
          <div className="rec-right">
            <AlgorithmGuard />
            <LLMExplanation />
          </div>
        </div>
      )}

      {/* ── SCREEN 2: EXECUTE ───────────────────────────────── */}
      {step === 'Execute' && (
        <div className="screen-execute">
          {/* Dominant: Gantt Chart */}
          <div className="exec-gantt">
            <MainGantt events={events} currentTick={tick} maxTick={maxTick} algo={algoKey} />
          </div>

          {/* Bottom strip: info card + process state + lanes */}
          <div className="exec-bottom">
            <ExecuteInfoCard events={events} tick={tick} algo={algoKey} />
            <ProcessState events={events} currentTick={tick} />
            <ProcessLanes events={events} currentTick={tick} maxTick={maxTick} algo={algoKey} />
          </div>

          {/* Collapsed debug trace */}
          <div className={`exec-debug card ${debugOpen ? 'exec-debug-open' : ''}`}>
            <button
              className="exec-debug-toggle"
              onClick={() => setDebugOpen(o => !o)}
            >
              <span>{debugOpen ? '▾' : '▸'}</span>
              Debug Trace Events
              <span className="exec-debug-count">{events.filter(e => e.tick <= tick).length} events @ tick {tick}</span>
            </button>
            {debugOpen && (
              <div className="exec-debug-body">
                <TraceStack events={events} currentTick={tick} maxEvents={maxTraceEvents} />
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── SCREEN 3: EVALUATE ──────────────────────────────── */}
      {step === 'Evaluate' && (
        <div className="screen-evaluate">
          {/* Top row: Verdict (wider) + Correction & Insight (narrower) */}
          <div className="eval-top">
            <EvaluationResult />
            <LLMExplanation compact />
          </div>

          {/* Bottom: Metric (left) + Comparison (right) side by side */}
          <div className="eval-bottom">
            <MetricVisualization />
            <AlgorithmComparison />
          </div>
        </div>
      )}

      <UITestControls {...utcProps} />
    </div>
  )
}
