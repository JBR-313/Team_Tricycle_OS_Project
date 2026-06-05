export const PROC_COLORS = {
  1: '#6366f1', 2: '#f43f5e', 3: '#10b981', 4: '#f59e0b', 5: '#3b82f6',
  6: '#8b5cf6', 7: '#ec4899', 8: '#14b8a6',
}

export const ALGO_COLORS = {
  RR:       '#6366f1',
  FCFS:     '#f43f5e',
  Priority: '#10b981',
  MLFQ:     '#f59e0b',
  SJF:      '#3b82f6',
  SRTF:     '#8b5cf6',
}

// ── Simulated-time display layer ──────────────────────────────────────────────
// The underlying trace uses xv6 scheduler *ticks*. For presentation we display
// a *simulated time* in milliseconds so the replay reads as a time-dilated
// visualization rather than an implementation-specific tick counter. This is a
// DISPLAY-ONLY scale; it never changes the trace schema or any metric formula.
export const TICK_MS = 10

export function tickToMs(tick) {
  const t = Number.isFinite(tick) ? tick : 0
  return Math.round(t * TICK_MS)
}

// "80 ms" — the canonical user-facing time label.
export function formatMs(tick) {
  return `${tickToMs(tick)} ms`
}

// Caption shown near any simulated-time control, so the scale is never
// mistaken for real wall-clock time or live kernel control.
export const SIM_TIME_CAPTION =
  'Displayed time is scaled for visualization. The underlying trace still uses xv6 scheduler ticks.'
