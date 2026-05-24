import Card from './Card.jsx'
import { PROC_COLORS } from '../data/demoData.js'

const ET_ICON = {
  DISPATCH: '▶', PREEMPT: '⏸', EXIT: '✓',
  ARRIVE: '→', WAKEUP: '↑', QUEUE_CHANGE: '⇄', CORRECTION_APPLIED: '⚡',
}
const ET_CLS = {
  PREEMPT: 'ev-preempt', EXIT: 'ev-exit',
  ARRIVE: 'ev-arrive', CORRECTION_APPLIED: 'ev-correction', WAKEUP: 'ev-wakeup',
}

const STATE_BADGE = {
  DISPATCH:  { text: 'RUNNING',  color: '#1d4ed8', bg: 'rgba(219,234,254,0.85)' },
  PREEMPT:   { text: 'PREEMPTED', color: '#dc2626', bg: 'rgba(254,226,226,0.85)' },
  EXIT:      { text: 'EXITED',   color: '#059669', bg: 'rgba(209,250,229,0.85)' },
  ARRIVE:    { text: 'ARRIVED',  color: '#7c3aed', bg: 'rgba(237,233,254,0.85)' },
  WAKEUP:    { text: 'WAKEUP',   color: '#0284c7', bg: 'rgba(224,242,254,0.85)' },
  QUEUE_CHANGE: { text: 'QUEUE', color: '#b45309', bg: 'rgba(254,243,199,0.85)' },
  CORRECTION_APPLIED: { text: 'CORRECTED', color: '#d97706', bg: 'rgba(255,251,235,0.85)' },
}

export default function TraceStack({ events, currentTick, maxEvents = 5, large = false }) {
  const visible = events.filter(e => e.tick <= currentTick)
  const sorted  = [...visible].sort((a, b) => b.tick - a.tick || b.pid - a.pid)
  const recent  = sorted.slice(0, maxEvents)
  const totalCount = sorted.length

  if (recent.length === 0) {
    return (
      <Card label={`Trace Events · Latest ${maxEvents}${large ? ' — Trace Mode' : ''}`} className={`card-trace${large ? ' card-trace-large' : ''}`}>
        <div className="trace-empty">
          <span className="trace-empty-icon">◎</span>
          <span>No events yet — move the slider</span>
        </div>
      </Card>
    )
  }

  return (
    <Card label={`Trace Events · Latest ${maxEvents}${large ? ' — Trace Mode' : ''}`} className={`card-trace${large ? ' card-trace-large' : ''}`}>
      <div className="trace-stack-wrap">
      <div className="trace-stack">
        {recent.map((ev, i) => {
          const pid    = ev.pid
          const et     = ev.event
          const icon   = ET_ICON[et] || '·'
          const pidStr = pid > 0 ? `P${pid}` : 'SYS'
          const clr    = PROC_COLORS[pid] || '#64748b'
          const badge  = STATE_BADGE[et]
          const detail = [ev.state, ev.reason].filter(Boolean).join(' · ')

          return (
            <div
              key={`${ev.tick}-${pid}-${et}-${i}`}
              className={`notif-card depth-${i} ${ET_CLS[et] || ''}`}
            >
              <div className="notif-header">
                <div className="notif-left">
                  <span className="notif-pid-dot" style={{ background: clr }} />
                  <span className="notif-title" style={{ color: clr }}>
                    {pidStr} — {et}
                  </span>
                </div>
                <div className="notif-right">
                  {badge && i === 0 && (
                    <span className="notif-badge" style={{ color: badge.color, background: badge.bg }}>
                      {badge.text}
                    </span>
                  )}
                  <span className="notif-tick">tick {ev.tick}</span>
                </div>
              </div>
              {i < 2 && detail && (
                <div className="notif-body">{detail}</div>
              )}
            </div>
          )
        })}
      </div>
      {totalCount > maxEvents && <div className="trace-fade-out" />}
      </div>

      {totalCount > maxEvents && (
        <div className="trace-older-hint">
          +{totalCount - maxEvents} earlier events at tick ≤ {currentTick}
        </div>
      )}
    </Card>
  )
}
