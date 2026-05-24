import { useState, useEffect } from 'react'

const PILLS = [
  { label: 'Workload Analysis', color: 'rgba(99,102,241,0.13)', text: '#4f46e5' },
  { label: 'Algorithm Advisor', color: 'rgba(236,72,153,0.12)', text: '#db2777' },
  { label: 'Trace Explainer',   color: 'rgba(16,185,129,0.12)', text: '#059669' },
  { label: 'Metrics Evaluator', color: 'rgba(245,158,11,0.13)', text: '#b45309' },
]

const TAGLINES = [
  'LLM suggests. Guard validates. xv6 executes.',
  'From terminal trace logs to visual OS insight.',
  'Turn scheduling chaos into scheduling clarity.',
]

export default function HeroSection({ onEnterDashboard, events, algo, currentTick, maxTick }) {
  const [taglineIdx, setTaglineIdx] = useState(0)
  const [fade, setFade] = useState(true)

  useEffect(() => {
    const id = setInterval(() => {
      setFade(false)
      setTimeout(() => {
        setTaglineIdx(i => (i + 1) % TAGLINES.length)
        setFade(true)
      }, 300)
    }, 3200)
    return () => clearInterval(id)
  }, [])

  // mini gantt preview from events
  const visible = (events || []).filter(e => e.tick <= currentTick)
  const dispatched = {}
  const segs = []
  for (const ev of visible) {
    if (ev.event === 'DISPATCH') dispatched[ev.pid] = ev.tick
    else if (['PREEMPT', 'SLEEP', 'EXIT'].includes(ev.event) && dispatched[ev.pid] != null) {
      segs.push({ pid: ev.pid, start: dispatched[ev.pid], end: ev.tick })
      delete dispatched[ev.pid]
    }
  }
  for (const [pid, start] of Object.entries(dispatched)) segs.push({ pid: Number(pid), start, end: currentTick })
  const span = Math.max(maxTick || 1, 1)

  const PROC_COLORS = { 1:'#6366f1', 2:'#f43f5e', 3:'#10b981', 4:'#8b5cf6', 5:'#f59e0b', 6:'#0ea5e9', 7:'#ec4899', 8:'#14b8a6' }

  return (
    <div className="hero-shell">
      {/* ambient blobs */}
      <div className="hero-blob hero-blob-1" />
      <div className="hero-blob hero-blob-2" />
      <div className="hero-blob hero-blob-3" />

      <div className="hero-content">
        {/* badge */}
        <div className="hero-badge">
          <span className="hero-badge-dot" />
          UI Test Dashboard · Static Fixture Mode
        </div>

        {/* title */}
        <h1 className="hero-title">
          LLM <span className="hero-title-accent">Sched</span> Copilot
        </h1>

        {/* rotating tagline */}
        <p className="hero-tagline" style={{ opacity: fade ? 1 : 0, transition: 'opacity 0.3s ease' }}>
          {TAGLINES[taglineIdx]}
        </p>

        {/* feature pills */}
        <div className="hero-pills">
          {PILLS.map(p => (
            <span key={p.label} className="hero-pill" style={{ background: p.color, color: p.text }}>
              {p.label}
            </span>
          ))}
        </div>

        {/* CTA */}
        <button className="hero-cta" onClick={onEnterDashboard}>
          Open Dashboard
          <span className="hero-cta-arrow">→</span>
        </button>

        {/* mini Gantt preview */}
        <div className="hero-preview-card">
          <div className="hero-preview-label">
            <span className="hero-preview-dot" />
            {algo} · tick {currentTick} / {maxTick}
          </div>
          <div className="hero-gantt">
            {segs.filter(s => s.end > s.start).map((s, i) => (
              <div
                key={i}
                className="hero-gantt-seg"
                style={{
                  left: `${(s.start / span) * 100}%`,
                  width: `${Math.max((s.end - s.start) / span * 100, 0.5)}%`,
                  background: PROC_COLORS[s.pid] || '#94a3b8',
                }}
                title={`P${s.pid}: ${s.start}→${s.end}`}
              />
            ))}
            <div className="hero-tick-marker" style={{ left: `${(currentTick / span) * 100}%` }} />
          </div>
          <div className="hero-gantt-legend">
            {[...new Set(segs.map(s => s.pid))].sort((a, b) => a - b).map(pid => (
              <div key={pid} className="hero-gantt-legend-item">
                <div className="hero-gantt-dot" style={{ background: PROC_COLORS[pid] || '#94a3b8' }} />
                <span>P{pid}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
