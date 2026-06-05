import Card from './Card.jsx'
import { PROC_COLORS } from './constants.js'

/**
 * ProcessState — Page 2 educational state-transition diagram.
 *
 * Layout (viewBox 0..100, preserveAspectRatio="none" — boxes are
 * absolutely positioned over the SVG using the same percentage system):
 *
 *   ┌────────┐
 *   │ READY  │──────────┐
 *   └────┬───┘          │
 *        │              │
 *        ▼              ▼
 *   ┌────────┐    ┌──────────┐
 *   │RUNNING │◀───│ WAITING  │
 *   └────┬───┘    └──────────┘
 *        │
 *        ▼
 *   ┌────────────┐
 *   │ TERMINATED │
 *   └────────────┘
 *
 * Transitions:
 *   DISPATCH  → READY → RUNNING       (dispatch)
 *   PREEMPT   → RUNNING → READY        (preempt, same line, reversed)
 *   SLEEP     → RUNNING → WAITING      (L-shape, right then up)
 *   WAKEUP    → WAITING → READY        (L-shape, up then left)
 *   EXIT      → RUNNING → TERMINATED   (vertical)
 *
 * The path matching the latest applicable event gets the `.active` class,
 * which turns it indigo and runs a stroke-dashoffset animation so a series
 * of dashes appears to flow along the path in the transition direction.
 */

function getStates(events) {
  const st = {}
  for (const ev of events) {
    const { pid, event: et } = ev
    if (pid < 0) continue
    if (['ARRIVE', 'PREEMPT', 'WAKEUP'].includes(et)) st[pid] = 'Ready'
    else if (et === 'DISPATCH') st[pid] = 'Running'
    else if (et === 'SLEEP')    st[pid] = 'Waiting'
    else if (et === 'EXIT')     st[pid] = 'Terminated'
  }
  return st
}

const NODE_STYLE = {
  Ready:      { fg: '#7c3aed', bg: 'rgba(237,233,254,0.95)', border: '#c4b5fd' },
  Running:    { fg: '#1d4ed8', bg: 'rgba(219,234,254,0.95)', border: '#93c5fd' },
  Waiting:    { fg: '#b45309', bg: 'rgba(254,243,199,0.95)', border: '#fcd34d' },
  Terminated: { fg: '#475569', bg: 'rgba(241,245,249,0.95)', border: '#cbd5e1' },
}

// Trace event → transition path identifier.
const EVENT_TO_PATH = {
  DISPATCH: 'dispatch',  // READY → RUNNING
  PREEMPT:  'preempt',   // RUNNING → READY
  SLEEP:    'sleep',     // RUNNING → WAITING
  WAKEUP:   'wakeup',    // WAITING → READY
  EXIT:     'exit',      // RUNNING → TERMINATED
}

function Tokens({ pids }) {
  if (!pids.length) return <div className="pstate-tokens-empty">—</div>
  return (
    <div className="pstate-tokens">
      {pids.map(pid => (
        <div
          key={pid}
          className="pstate-token"
          style={{ background: PROC_COLORS[pid] || '#94a3b8' }}
          title={`P${pid}`}
        >
          P{pid}
        </div>
      ))}
    </div>
  )
}

function Box({ name, pids, posClass }) {
  const style = NODE_STYLE[name]
  return (
    <div
      className={`pstate-box ${posClass}`}
      style={{ background: style.bg, borderColor: style.border }}
    >
      <div className="pstate-box-name" style={{ color: style.fg }}>{name}</div>
      <Tokens pids={pids} />
    </div>
  )
}

export default function ProcessState({ events, currentTick }) {
  const visible = events.filter(e => e.tick <= currentTick)
  const stMap   = getStates(visible)
  const groups  = { Ready: [], Running: [], Waiting: [], Terminated: [] }
  for (const [pid, st] of Object.entries(stMap)) {
    if (groups[st]) groups[st].push(Number(pid))
  }
  Object.values(groups).forEach(g => g.sort((a, b) => a - b))

  // Latest transition event drives the active animation (no caption text — the
  // animated connector itself communicates the transition).
  let activePath = null
  for (let i = visible.length - 1; i >= 0; i--) {
    const ev = visible[i]
    if (ev.event in EVENT_TO_PATH && ev.pid >= 0) {
      activePath = EVENT_TO_PATH[ev.event]
      break
    }
  }

  const cls = (id) => `pstate-path${activePath === id ? ' active' : ''}`
  const labelCls = (id) => `pstate-label${activePath === id ? ' active' : ''}`

  return (
    <Card label="Process State" className="card-pstate">
      <div className="pstate-diagram">
        <svg
          className="pstate-svg"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <defs>
            <marker id="pstate-arrow" viewBox="0 0 10 10" refX="9" refY="5"
                    markerWidth="5" markerHeight="5" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#9aa6b9" />
            </marker>
            <marker id="pstate-arrow-active" viewBox="0 0 10 10" refX="9" refY="5"
                    markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#0a3069" />
            </marker>
          </defs>

          {/* READY → RUNNING : vertical, downward arrow (dispatch).
              Active when DISPATCH is the latest event. */}
          <line
            x1="25" y1="20" x2="25" y2="51"
            className={cls('dispatch')}
            vectorEffect="non-scaling-stroke"
            markerEnd={activePath === 'dispatch'
              ? 'url(#pstate-arrow-active)'
              : 'url(#pstate-arrow)'}
          />

          {/* RUNNING → READY : same column, upward arrow (preempt).
              Drawn slightly offset so it doesn't overlap the dispatch line. */}
          <line
            x1="32" y1="51" x2="32" y2="21"
            className={cls('preempt')}
            vectorEffect="non-scaling-stroke"
            markerEnd={activePath === 'preempt'
              ? 'url(#pstate-arrow-active)'
              : 'url(#pstate-arrow)'}
          />

          {/* RUNNING → TERMINATED : vertical, downward (exit). */}
          <line
            x1="28" y1="68" x2="28" y2="79"
            className={cls('exit')}
            vectorEffect="non-scaling-stroke"
            markerEnd={activePath === 'exit'
              ? 'url(#pstate-arrow-active)'
              : 'url(#pstate-arrow)'}
          />

          {/* RUNNING → WAITING : L-shape — right then up (sleep). */}
          <polyline
            points="43,57 75,57 75,44"
            fill="none"
            className={cls('sleep')}
            vectorEffect="non-scaling-stroke"
            markerEnd={activePath === 'sleep'
              ? 'url(#pstate-arrow-active)'
              : 'url(#pstate-arrow)'}
          />

          {/* WAITING → READY : L-shape — up then left (wakeup). */}
          <polyline
            points="75,28 75,12 44,12"
            fill="none"
            className={cls('wakeup')}
            vectorEffect="non-scaling-stroke"
            markerEnd={activePath === 'wakeup'
              ? 'url(#pstate-arrow-active)'
              : 'url(#pstate-arrow)'}
          />
        </svg>

        {/* State boxes — absolute over the SVG, percentages match viewBox. */}
        <Box name="Ready"      pids={groups.Ready}      posClass="pstate-ready" />
        <Box name="Waiting"    pids={groups.Waiting}    posClass="pstate-waiting" />
        <Box name="Running"    pids={groups.Running}    posClass="pstate-running" />
        <Box name="Terminated" pids={groups.Terminated} posClass="pstate-terminated" />

        {/* Transition labels — small, attached to each connector. */}
        <span className={`${labelCls('dispatch')} pstate-label-dispatch`}>dispatch</span>
        <span className={`${labelCls('preempt')} pstate-label-preempt`}>preempt</span>
        <span className={`${labelCls('sleep')} pstate-label-sleep`}>sleep</span>
        <span className={`${labelCls('wakeup')} pstate-label-wakeup`}>wakeup</span>
        <span className={`${labelCls('exit')} pstate-label-exit`}>exit</span>
      </div>
    </Card>
  )
}
