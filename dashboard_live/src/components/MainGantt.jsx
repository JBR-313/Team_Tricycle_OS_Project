import Card from './Card.jsx'
import { PROC_COLORS, tickToMs } from './constants.js'

function buildSegments(events, capTick) {
  const dispatched = {}
  const segs = []
  for (const ev of events) {
    if (ev.event === 'DISPATCH') {
      dispatched[ev.pid] = ev.tick
    } else if (['PREEMPT', 'SLEEP', 'EXIT'].includes(ev.event) && dispatched[ev.pid] != null) {
      segs.push({ pid: ev.pid, start: dispatched[ev.pid], end: ev.tick })
      delete dispatched[ev.pid]
    }
  }
  for (const [pid, start] of Object.entries(dispatched)) {
    segs.push({ pid: Number(pid), start, end: capTick })
  }
  return segs.filter(s => s.end > s.start).sort((a, b) => a.start - b.start)
}

export default function MainGantt({ events, currentTick, maxTick, algo }) {
  const visible = events.filter(e => e.tick <= currentTick)
  const segs    = buildSegments(visible, currentTick)
  const span    = Math.max(maxTick, 1)

  const step = span <= 30 ? 5 : span <= 60 ? 10 : 20
  const ticks = []
  for (let t = 0; t <= span; t += step) ticks.push(t)

  const pids = [...new Set(segs.map(s => s.pid))].sort((a, b) => a - b)

  return (
    <Card label={`Gantt Chart · ${algo}`} className="card-gantt">
      <div className="gantt-bar-container">
        {segs.map((s, i) => {
          const w = ((s.end - s.start) / span) * 100
          const x = (s.start / span) * 100
          const label = w > 3 ? `P${s.pid}` : ''
          return (
            <div
              key={i}
              className="gantt-seg"
              title={`P${s.pid}: ${tickToMs(s.start)} ms → ${tickToMs(s.end)} ms`}
              style={{
                left: `${x}%`,
                width: `${w}%`,
                background: PROC_COLORS[s.pid] || '#94a3b8',
              }}
            >
              {label}
            </div>
          )
        })}
        {ticks.filter(t => t > 0).map(t => (
          <div key={t} className="gantt-grid-line" style={{ left: `${(t / span) * 100}%` }} />
        ))}
        <div className="gantt-tick-marker" style={{ left: `${(currentTick / span) * 100}%` }}>
          <span className="gantt-tick-marker-label">{tickToMs(currentTick)} ms</span>
        </div>
      </div>
      <div className="gantt-tick-axis">
        {ticks.map(t => (
          <span key={t} className="gantt-tick-num" style={{ left: `${(t / span) * 100}%` }}>{tickToMs(t)}</span>
        ))}
      </div>
      <div className="gantt-legend">
        {pids.map(pid => (
          <div key={pid} className="gantt-legend-item">
            <div className="gantt-legend-dot" style={{ background: PROC_COLORS[pid] || '#94a3b8' }} />
            <span>P{pid}</span>
          </div>
        ))}
        <div className="gantt-legend-item" style={{ marginLeft: 4 }}>
          <div className="gantt-legend-dot" style={{ background: 'rgba(99,102,241,0.70)', width: 2, height: 8, borderRadius: 1 }} />
          <span>{tickToMs(currentTick)} ms elapsed</span>
        </div>
      </div>
    </Card>
  )
}
