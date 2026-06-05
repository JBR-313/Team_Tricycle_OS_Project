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
  return segs.filter(s => s.end > s.start)
}

export default function ProcessLanes({ events, currentTick, maxTick, algo }) {
  const visible = events.filter(e => e.tick <= currentTick)
  const segs    = buildSegments(visible, currentTick)
  const span    = Math.max(maxTick, 1)

  const pids = [...new Set(events.filter(e => e.pid > 0).map(e => e.pid))].sort((a, b) => a - b)

  const step = span <= 30 ? 5 : span <= 60 ? 10 : 20
  const gridTicks = []
  for (let t = step; t < span; t += step) gridTicks.push(t)
  const axisTicks = [0, ...gridTicks]

  return (
    <Card label={`Process Lanes · ${algo}`} className="card-lanes">
      <div className="lanes-chart">
        {pids.map(pid => {
          const pidSegs = segs.filter(s => s.pid === pid)
          return (
            <div key={pid} className="lane-row">
              <span className="lane-label">P{pid}</span>
              <div className="lane-track">
                {pidSegs.map((s, i) => {
                  const w = ((s.end - s.start) / span) * 100
                  // Label inside the bar when it is wide enough; otherwise the
                  // tooltip carries the timing (very short slices stay readable).
                  const inLabel = w >= 8 ? `${tickToMs(s.start)}–${tickToMs(s.end)} ms` : ''
                  return (
                    <div
                      key={i}
                      className="lane-seg"
                      style={{
                        left:  `${(s.start / span) * 100}%`,
                        width: `${w}%`,
                        background: PROC_COLORS[s.pid] || '#94a3b8',
                      }}
                      title={`P${s.pid}: ${tickToMs(s.start)} ms → ${tickToMs(s.end)} ms`}
                    >
                      {inLabel && <span className="lane-seg-label">{inLabel}</span>}
                    </div>
                  )
                })}
                {gridTicks.map(t => (
                  <div key={t} className="gantt-grid-line" style={{ left: `${(t / span) * 100}%` }} />
                ))}
                <div className="lane-tick-marker" style={{ left: `${(currentTick / span) * 100}%` }} />
              </div>
            </div>
          )
        })}
        <div className="lanes-tick-axis">
          <div className="lanes-tick-offset">
            {axisTicks.map(t => (
              <span key={t} className="lanes-tick-num" style={{ left: `${(t / span) * 100}%` }}>{tickToMs(t)}</span>
            ))}
          </div>
        </div>
      </div>
    </Card>
  )
}
