import Card from './Card.jsx'
import { PROC_COLORS } from './constants.js'

/**
 * MLFQQueuePanel — visible only when algo === 'MLFQ'.
 * Derives all state from `events` up to currentTick, no new fetch.
 *
 * Sub-views:
 *   A. Current queue snapshot (Q0/Q1/Q2 lanes with PID chips)
 *   B. Recent Queue Changes (last 5 QUEUE_CHANGE entries)
 *   C. Per-queue dispatch share (3 bars)
 */
export default function MLFQQueuePanel({ events, currentTick, algo }) {
  if (algo !== 'MLFQ') {
    return (
      <Card label="Multilevel Queue" className="card-mlfq-queue card-mlfq-inactive">
        <div className="mlfq-inactive-msg">
          MLFQ queue view appears when <strong>MLFQ</strong> is selected.
        </div>
      </Card>
    )
  }

  const visible = events.filter(e => (e.tick ?? 0) <= currentTick)
  const hasQueueData = visible.some(e =>
    e.event === 'QUEUE_CHANGE' ||
    (e.event === 'ARRIVE'   && e.queue   != null) ||
    (e.event === 'DISPATCH' && e.queue   != null)
  )
  if (!hasQueueData) {
    return (
      <Card label="Multilevel Queue" className="card-mlfq-queue card-mlfq-inactive">
        <div className="mlfq-inactive-msg">MLFQ queue data unavailable.</div>
      </Card>
    )
  }

  // ─── A. Current queue snapshot ────────────────────────────────────────────
  // For each pid with at least one event, take the most-recent known queue.
  // Also track whether the pid is currently RUNNING (most-recent DISPATCH
  // without a later PREEMPT/EXIT).
  const pidQueue = new Map()       // pid -> queue level (int)
  const pidStatus = new Map()      // pid -> 'RUNNING' | 'RUNNABLE' | 'DONE'
  for (const e of visible) {
    if (e.pid == null || e.pid < 0) continue
    if (e.event === 'ARRIVE') {
      pidQueue.set(e.pid, e.queue ?? 0)
      pidStatus.set(e.pid, 'RUNNABLE')
    } else if (e.event === 'DISPATCH') {
      if (e.queue != null) pidQueue.set(e.pid, e.queue)
      pidStatus.set(e.pid, 'RUNNING')
    } else if (e.event === 'PREEMPT') {
      if (e.queue != null) pidQueue.set(e.pid, e.queue)
      pidStatus.set(e.pid, 'RUNNABLE')
    } else if (e.event === 'QUEUE_CHANGE') {
      if (e.to_queue != null) pidQueue.set(e.pid, e.to_queue)
    } else if (e.event === 'EXIT') {
      pidStatus.set(e.pid, 'DONE')
    }
  }

  const queueLanes = [0, 1, 2]
  const pidsByQueue = new Map(queueLanes.map(q => [q, []]))
  for (const [pid, q] of pidQueue.entries()) {
    if (pidStatus.get(pid) === 'DONE') continue
    const lane = pidsByQueue.get(q) ?? pidsByQueue.get(2)
    lane.push(pid)
  }
  for (const arr of pidsByQueue.values()) arr.sort((a, b) => a - b)

  // ─── B. Recent queue changes ──────────────────────────────────────────────
  const recentChanges = visible
    .filter(e => e.event === 'QUEUE_CHANGE')
    .slice(-5)
    .reverse()

  // ─── C. Per-queue dispatch share ──────────────────────────────────────────
  const dispatchByQueue = { 0: 0, 1: 0, 2: 0 }
  for (const e of visible) {
    if (e.event !== 'DISPATCH') continue
    const q = (e.queue ?? 0)
    if (q in dispatchByQueue) dispatchByQueue[q] += 1
  }
  const totalDispatches = Object.values(dispatchByQueue).reduce((a, b) => a + b, 0) || 1
  const sharePct = (q) => Math.round((dispatchByQueue[q] / totalDispatches) * 100)

  const QUEUE_QUANTUM = { 0: 2, 1: 4, 2: 8 }

  return (
    <Card label="MLFQ · Queue State" className="card-mlfq-queue">
      {/* A. Lanes */}
      <div className="mlfq-lanes">
        {queueLanes.map(q => (
          <div key={q} className="mlfq-lane">
            <div className="mlfq-lane-head">
              <span className="mlfq-lane-name">Q{q}</span>
              <span className="mlfq-lane-meta">quantum = {QUEUE_QUANTUM[q]}</span>
            </div>
            <div className="mlfq-lane-chips">
              {pidsByQueue.get(q).length === 0
                ? <span className="mlfq-empty">— empty —</span>
                : pidsByQueue.get(q).map(pid => (
                    <span
                      key={pid}
                      className={`mlfq-chip ${pidStatus.get(pid) === 'RUNNING' ? 'running' : ''}`}
                      style={{ background: PROC_COLORS[pid] || '#94a3b8' }}
                      title={`P${pid} · ${pidStatus.get(pid) ?? 'RUNNABLE'}`}
                    >P{pid}</span>
                  ))}
            </div>
          </div>
        ))}
      </div>

      {/* C. Dispatch share */}
      <div className="mlfq-share">
        <div className="mlfq-share-label">Dispatch share ({totalDispatches} total)</div>
        {queueLanes.map(q => (
          <div key={q} className="mlfq-share-row">
            <span className="mlfq-share-q">Q{q}</span>
            <div className="mlfq-share-bar">
              <div className="mlfq-share-fill" style={{ width: `${sharePct(q)}%` }} />
            </div>
            <span className="mlfq-share-pct">{sharePct(q)}%</span>
          </div>
        ))}
      </div>

      {/* B. Recent queue changes */}
      <div className="mlfq-changes">
        <div className="mlfq-share-label">Recent queue changes</div>
        {recentChanges.length === 0
          ? <span className="mlfq-empty">— none yet —</span>
          : (
            <ul className="mlfq-change-list">
              {recentChanges.map((e, i) => (
                <li key={i}>
                  <span className="mlfq-change-tick">t={e.tick}</span>
                  <span className="mlfq-change-pid">P{e.pid}</span>
                  <span className="mlfq-change-arrow">Q{e.from_queue} → Q{e.to_queue}</span>
                  <span className="mlfq-change-reason">{e.reason || '—'}</span>
                </li>
              ))}
            </ul>
          )}
      </div>
    </Card>
  )
}
