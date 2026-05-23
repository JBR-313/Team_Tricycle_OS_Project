import { useState, useMemo } from 'react'
import './App.css'

import { traces, ALGOS } from './data/demoData.js'

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

export default function App() {
  const [algo, setAlgo]   = useState('MLFQ')
  const [tick, setTick]   = useState(30)

  const algoKey    = ALGOS.includes(algo) ? algo : 'MLFQ'
  // Trace lookup: 'Priority' → stored as 'Priority' in traces
  const traceKey   = Object.keys(traces).find(k => k.toLowerCase() === algoKey.toLowerCase()) || 'MLFQ'
  const events     = traces[traceKey] || []
  const maxTick    = useMemo(() => Math.max(...events.map(e => e.tick), 1), [events])

  function handleAlgoChange(newAlgo) {
    setAlgo(newAlgo)
    // Reset tick to ~55% of the new algo's max tick
    const newEvents = traces[Object.keys(traces).find(k => k.toLowerCase() === newAlgo.toLowerCase())] || []
    const newMax    = Math.max(...newEvents.map(e => e.tick), 1)
    setTick(Math.round(newMax * 0.55))
  }

  return (
    <div className="dashboard-shell">
      <Header
        algo={algo}
        onAlgoChange={handleAlgoChange}
        currentTick={tick}
        maxTick={maxTick}
        onTickChange={setTick}
      />

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
          <MainGantt  events={events} currentTick={tick} maxTick={maxTick} algo={algo} />
          <ProcessState events={events} currentTick={tick} />
          <TraceStack events={events} currentTick={tick} />
        </div>

        {/* ── RIGHT COLUMN ── */}
        <div className="dashboard-col">
          <ProcessLanes  events={events} currentTick={tick} maxTick={maxTick} algo={algo} />
          <WorkloadSummary />
          <AlgorithmComparison />
          <MetricVisualization />
        </div>
      </div>
    </div>
  )
}
