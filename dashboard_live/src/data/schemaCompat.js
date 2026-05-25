// Schema compatibility — backward-compatible reader layer.
//
// Mirrors tools/schema_compat.py. Data files in the repo carry either spelling
// for several keys (recommended_scheduling_algorithm vs algorithm, tick vs
// time, algo vs algorithm, backend vs legacy mode). These helpers let the
// React app READ either spelling without renaming anything. All functions are
// defensive against null/undefined inputs and never throw.

export const CANONICAL_ALGOS = ['RR', 'FCFS', 'PRIORITY', 'MLFQ', 'SJF', 'SRTF']

// 'Priority' -> 'PRIORITY', 'mlfq' -> 'MLFQ'. Falsy -> 'RR'.
export function normalizeAlgo(name) {
  if (!name) return 'RR'
  return String(name).trim().toUpperCase()
}

// rec.recommended_scheduling_algorithm || rec.algorithm || fallback, normalized.
export function getRecommendedAlgorithm(rec, fallback = 'RR') {
  const r = rec || {}
  const name = r.recommended_scheduling_algorithm || r.algorithm
  return name ? normalizeAlgo(name) : normalizeAlgo(fallback)
}

// guard.scheduling_algorithm || guard.algorithm || fallback, normalized.
export function getGuardAlgorithm(guard, fallback = 'RR') {
  const g = guard || {}
  const name = g.scheduling_algorithm || g.algorithm
  return name ? normalizeAlgo(name) : normalizeAlgo(fallback)
}

// ev.tick ?? ev.time ?? null.
export function getEventTick(ev) {
  const e = ev || {}
  return e.tick ?? e.time ?? null
}

// normalizeAlgo(ev.algo || ev.algorithm), or null when neither is present.
export function getEventAlgo(ev) {
  const e = ev || {}
  const name = e.algo || e.algorithm
  return name ? normalizeAlgo(name) : null
}

// manifest.backend (lowercased) || (manifest.mode === 'xv6-log' ? 'xv6' : 'simulator').
export function getBackend(manifest) {
  const m = manifest || {}
  if (m.backend) return String(m.backend).trim().toLowerCase()
  return m.mode === 'xv6-log' ? 'xv6' : 'simulator'
}
