import Card from './Card.jsx'
import { PROC_COLORS, tickToMs } from './constants.js'

const ET_ICON = {
  DISPATCH: '▶', PREEMPT: '⏸', EXIT: '✓',
  ARRIVE: '→', WAKEUP: '↑', QUEUE_CHANGE: '⇄', CORRECTION_APPLIED: '⚡',
}
const ET_CLS = {
  PREEMPT: 'ev-preempt', EXIT: 'ev-exit',
  ARRIVE: 'ev-arrive', CORRECTION_APPLIED: 'ev-correction', WAKEUP: 'ev-wakeup',
}

// Pre-run kernel-parameter evidence events. They carry no tick (they are
// applied before the workload runs), so they are shown once in a compact
// evidence strip rather than interleaved into the time-ordered log.
const EVIDENCE_EVENTS = new Set([
  'RR_PARAMS', 'PRIORITY_PARAMS', 'MLFQ_PARAMS',
  'PREDICTOR_PARAMS', 'BURST_HINT_APPLIED',
])

function evidenceSummary(ev) {
  switch (ev.event) {
    case 'RR_PARAMS':        return `RR quantum=${ev.quantum}`
    case 'PRIORITY_PARAMS':  return `Priority aging=${ev.aging_threshold}`
    case 'MLFQ_PARAMS':      return `MLFQ queues=${ev.queues} q=${ev.quantum}${ev.boost_interval != null ? ` boost=${ev.boost_interval}` : ''}`
    case 'PREDICTOR_PARAMS': return `Predictor α=${ev.alpha} init=${ev.initial} [${ev.min},${ev.max}]`
    case 'BURST_HINT_APPLIED': return `P${ev.pid} burst hint=${ev.predicted_burst}`
    default: return ev.event
  }
}
const STATE_BADGE = {
  DISPATCH:  { text: 'RUNNING',    color: '#1d4ed8', bg: 'rgba(219,234,254,0.85)' },
  PREEMPT:   { text: 'PREEMPTED',  color: '#dc2626', bg: 'rgba(254,226,226,0.85)' },
  EXIT:      { text: 'EXITED',     color: '#059669', bg: 'rgba(209,250,229,0.85)' },
  ARRIVE:    { text: 'ARRIVED',    color: '#7c3aed', bg: 'rgba(237,233,254,0.85)' },
  WAKEUP:    { text: 'WAKEUP',     color: '#0284c7', bg: 'rgba(224,242,254,0.85)' },
  QUEUE_CHANGE:       { text: 'QUEUE',     color: '#b45309', bg: 'rgba(254,243,199,0.85)' },
  CORRECTION_APPLIED: { text: 'CORRECTED', color: '#d97706', bg: 'rgba(255,251,235,0.85)' },
}

export default function TraceStack({ events, currentTick }) {
  // Kernel-parameter evidence (pre-run config, no tick) — shown once up top.
  const evidence = events.filter(e => EVIDENCE_EVENTS.has(e.event))

  // Time-ordered scheduling events: only those with a real (integer) tick that
  // has been reached by the current replay time. Newest first (one consistent
  // direction). Simulated-ms labels.
  const visible = events.filter(
    e => Number.isInteger(e.tick) && e.tick <= currentTick && !EVIDENCE_EVENTS.has(e.event)
  )
  const sorted  = [...visible].sort((a, b) => b.tick - a.tick || b.pid - a.pid)
  const totalCount = sorted.length

  const EvidenceStrip = () => (
    evidence.length === 0 ? null : (
      <div className="trace-evidence">
        <span className="trace-evidence-label">Kernel params applied</span>
        <div className="trace-evidence-chips">
          {evidence.map((ev, i) => (
            <span key={i} className="trace-evidence-chip" title="Parameter applied to xv6 before the run">
              {evidenceSummary(ev)}
            </span>
          ))}
        </div>
      </div>
    )
  )

  if (totalCount === 0) {
    return (
      <Card label="Trace Log" className="card-trace">
        <EvidenceStrip />
        <div className="trace-empty">
          <span className="trace-empty-icon">◎</span>
          <span>No events yet — press Play to start the replay</span>
        </div>
      </Card>
    )
  }

  return (
    <Card label={`Trace Log · ${totalCount} event${totalCount === 1 ? '' : 's'}`} className="card-trace">
      <EvidenceStrip />
      <div className="trace-stack">
        {sorted.map((ev, i) => {
          const pid    = ev.pid
          const et     = ev.event
          const pidStr = pid > 0 ? `P${pid}` : 'SYS'
          const clr    = PROC_COLORS[pid] || '#64748b'
          const badge  = STATE_BADGE[et]
          const detail = [ev.state, ev.reason].filter(Boolean).join(' · ')
          return (
            <div key={`${ev.tick}-${pid}-${et}-${i}`} className={`notif-card ${ET_CLS[et] || ''}`}>
              <div className="notif-header">
                <div className="notif-left">
                  <span className="notif-pid-dot" style={{ background: clr }} />
                  <span className="notif-title" style={{ color: clr }}>{pidStr} — {et}</span>
                </div>
                <div className="notif-right">
                  {badge && (
                    <span className="notif-badge" style={{ color: badge.color, background: badge.bg }}>{badge.text}</span>
                  )}
                  <span className="notif-tick">{tickToMs(ev.tick)} ms</span>
                </div>
              </div>
              {detail && <div className="notif-body">{detail}</div>}
            </div>
          )
        })}
      </div>
    </Card>
  )
}
