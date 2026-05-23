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

const NODE_STYLE = {
  Ready:      { fg: '#7c3aed', bg: 'rgba(237,233,254,0.90)', border: '#c4b5fd' },
  Running:    { fg: '#1d4ed8', bg: 'rgba(219,234,254,0.90)', border: '#93c5fd' },
  Waiting:    { fg: '#b45309', bg: 'rgba(254,243,199,0.90)', border: '#fcd34d' },
  Terminated: { fg: '#64748b', bg: 'rgba(241,245,249,0.80)', border: '#cbd5e1' },
}

const PIPE_CLASS = {
  DISPATCH:          'pipe-dispatch',
  PREEMPT:           'pipe-preempt',
  QUEUE_CHANGE:      'pipe-preempt',
  EXIT:              'pipe-exit',
  SLEEP:             'pipe-sleep',
  WAKEUP:            'pipe-wakeup',
}

function Tokens({ pids }) {
  if (!pids.length) return <div className="flow-empty">—</div>
  return (
    <div className="flow-token-row">
      {pids.map(pid => (
        <div
          key={pid}
          className="flow-token"
          style={{ background: PROC_COLORS[pid] || '#94a3b8' }}
          title={`P${pid}`}
        >
          P{pid}
        </div>
      ))}
    </div>
  )
}

function Node({ name, pids, gridCol, gridRow }) {
  const { fg, bg, border } = NODE_STYLE[name]
  const extra = name === 'Running' ? ' flow-node-running' : ''
  return (
    <div
      className={`flow-node${extra}`}
      style={{ background: bg, borderColor: border, gridColumn: gridCol, gridRow }}
    >
      <div className="flow-node-name" style={{ color: fg }}>{name}</div>
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

  // Find the most recent event that corresponds to a known state transition
  const latestEvent = [...visible]
    .sort((a, b) => b.tick - a.tick || b.pid - a.pid)
    .find(ev => ev.event in PIPE_CLASS)?.event ?? null
  const pc = PIPE_CLASS[latestEvent] || ''

  const isRRPipe    = pc === 'pipe-dispatch' || pc === 'pipe-preempt'
  const isExitPipe  = pc === 'pipe-exit'
  const isSleepArc  = pc === 'pipe-sleep'
  const isWakeupArc = pc === 'pipe-wakeup'

  return (
    <Card label="Process State" className="card-pstate">
      {/*
        Grid (5 cols × 3 rows):
          [READY] [pipe] [RUNNING] [pipe] [TERMINATED]
                          (vert)
          [wakeup←] [←]  [WAITING] [→] [sleep→]
      */}
      <div className="flow-diagram">

        {/* ── Row 1 ── */}
        <Node name="Ready"      pids={groups.Ready}      gridCol={1} gridRow={1} />

        <div
          className={`flow-pipe-h${isRRPipe ? ` ${pc}` : ''}`}
          style={{ gridColumn: 2, gridRow: 1 }}
        >
          <span className="flow-pipe-label">dispatch ▶</span>
          <div className="flow-pipe-bar" />
          <span className="flow-pipe-label">◀ preempt</span>
        </div>

        <Node name="Running"    pids={groups.Running}    gridCol={3} gridRow={1} />

        <div
          className={`flow-pipe-h flow-pipe-exit${isExitPipe ? ' pipe-exit' : ''}`}
          style={{ gridColumn: 4, gridRow: 1 }}
        >
          <span className="flow-pipe-label">exit ▶</span>
          <div className="flow-pipe-bar" />
        </div>

        <Node name="Terminated" pids={groups.Terminated} gridCol={5} gridRow={1} />

        {/* ── Row 2: vertical connector ── */}
        <div
          className={`flow-vert-connector${isSleepArc ? ' pipe-sleep-vert' : ''}`}
          style={{ gridColumn: 3, gridRow: 2 }}
        >
          <div className="flow-vert-bar" />
        </div>

        {/* ── Row 3: wakeup arc | Waiting | sleep arc ── */}
        <div
          className={`flow-arc flow-arc-left${isWakeupArc ? ' pipe-wakeup' : ''}`}
          style={{ gridColumn: '1 / 3', gridRow: 3 }}
        >
          <span className="flow-arc-label">wakeup ▶</span>
          <div className="flow-arc-line" />
        </div>

        <Node name="Waiting"    pids={groups.Waiting}    gridCol={3} gridRow={3} />

        <div
          className={`flow-arc flow-arc-right${isSleepArc ? ' pipe-sleep' : ''}`}
          style={{ gridColumn: '4 / 6', gridRow: 3 }}
        >
          <div className="flow-arc-line" />
          <span className="flow-arc-label">◀ sleep</span>
        </div>

      </div>
    </Card>
  )
}
