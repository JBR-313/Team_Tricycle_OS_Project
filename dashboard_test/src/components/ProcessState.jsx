import Card from './Card.jsx'
import { PROC_COLORS } from '../data/demoData.js'

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

const STATE_STYLE = {
  Ready:      { fg: '#7c3aed', bg: 'rgba(237,233,254,0.90)', border: '#c4b5fd' },
  Running:    { fg: '#1d4ed8', bg: 'rgba(219,234,254,0.90)', border: '#93c5fd' },
  Waiting:    { fg: '#b45309', bg: 'rgba(254,243,199,0.90)', border: '#fcd34d' },
  Terminated: { fg: '#64748b', bg: 'rgba(241,245,249,0.80)', border: '#cbd5e1' },
}

const PIPE_CLASS = {
  DISPATCH:     'ps-active-dispatch',
  PREEMPT:      'ps-active-preempt',
  QUEUE_CHANGE: 'ps-active-preempt',
  EXIT:         'ps-active-exit',
  SLEEP:        'ps-active-sleep',
  WAKEUP:       'ps-active-wakeup',
}

function TokenRow({ pids }) {
  if (!pids.length) return <span className="ps-empty">—</span>
  return (
    <div className="ps-tokens">
      {pids.slice(0, 5).map(pid => (
        <span
          key={pid}
          className="ps-token"
          style={{ background: PROC_COLORS[pid] || '#94a3b8' }}
        >P{pid}</span>
      ))}
    </div>
  )
}

function Box({ label, pids, stateKey, col, row, pulse }) {
  const { fg, bg, border } = STATE_STYLE[stateKey]
  return (
    <div
      className={`ps-box${pulse ? ' ps-box-running' : ''}`}
      style={{ background: bg, borderColor: border, gridColumn: col, gridRow: row }}
    >
      <div className="ps-box-name" style={{ color: fg }}>{label}</div>
      <TokenRow pids={pids} />
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

  const latestEvent = [...visible]
    .sort((a, b) => b.tick - a.tick || b.pid - a.pid)
    .find(ev => ev.event in PIPE_CLASS)?.event ?? null
  const active = PIPE_CLASS[latestEvent] || ''

  return (
    <Card label="Process State" className="card-pstate">
      {/*
        Grid (5 cols × 3 rows):
          [READY] [conn-rr] [RUNNING] [conn-exit] [DONE]
                               [v]
          [wakeup arc←←←←←←←] [WAITING] [←←←←sleep arc]
      */}
      <div className={`ps-diagram ${active}`}>

        <Box label="READY"   pids={groups.Ready}       stateKey="Ready"      col={1} row={1} />

        <div className="ps-conn-h ps-conn-rr" style={{ gridColumn: 2, gridRow: 1 }}>
          <span className="ps-conn-top">dispatch ▸</span>
          <div className="ps-conn-line" />
          <span className="ps-conn-bot">◂ preempt</span>
        </div>

        <Box label="RUNNING" pids={groups.Running}    stateKey="Running"    col={3} row={1} pulse />

        <div className="ps-conn-h ps-conn-exit" style={{ gridColumn: 4, gridRow: 1 }}>
          <span className="ps-conn-top">exit ▸</span>
          <div className="ps-conn-line" />
        </div>

        <Box label="DONE"    pids={groups.Terminated} stateKey="Terminated" col={5} row={1} />

        <div className="ps-conn-v" style={{ gridColumn: 3, gridRow: 2 }}>
          <div className="ps-conn-vline" />
        </div>

        <div className="ps-conn-arc ps-conn-wakeup" style={{ gridColumn: '1 / 3', gridRow: 3 }}>
          <span className="ps-conn-arc-label">wakeup ▸</span>
          <div className="ps-conn-arc-line" />
          <div className="ps-pipe-elbow" />
        </div>

        <Box label="WAITING" pids={groups.Waiting}    stateKey="Waiting"    col={3} row={3} />

        <div className="ps-conn-arc ps-conn-sleep" style={{ gridColumn: '4 / 6', gridRow: 3 }}>
          <div className="ps-pipe-elbow" />
          <div className="ps-conn-arc-line" />
          <span className="ps-conn-arc-label">◂ sleep</span>
        </div>

      </div>
    </Card>
  )
}
