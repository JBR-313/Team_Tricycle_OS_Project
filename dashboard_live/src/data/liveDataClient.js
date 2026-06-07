import { normalizeTraceEvent, getEventTick } from './schemaCompat.js'

// The dashboard normally serves files from /live-data. When a snapshot
// profile is selected in the header the base is swapped to
// /live-data/snapshots/<profile>; on "Default" it is restored. The
// snapshots_manifest.json itself always lives at the root, regardless
// of the currently-selected base.
const DEFAULT_BASE = '/live-data'
let _base = DEFAULT_BASE

export function getLiveDataBase() { return _base }
export function setLiveDataBase(b) { _base = b || DEFAULT_BASE }
export function resetLiveDataBase() { _base = DEFAULT_BASE }
export { DEFAULT_BASE }

const ALGO_FILE_MAP = {
  RR:       'trace_rr.jsonl',
  FCFS:     'trace_fcfs.jsonl',
  Priority: 'trace_priority.jsonl',
  MLFQ:     'trace_mlfq.jsonl',
  SJF:      'trace_sjf.jsonl',
  SRTF:     'trace_srtf.jsonl',
}

export const ALGOS = Object.keys(ALGO_FILE_MAP)

async function fetchJson(path) {
  const res = await fetch(`${_base}/${path}`)
  if (!res.ok) throw new Error(`fetch failed: ${path} (${res.status})`)
  return res.json()
}

async function fetchText(path) {
  const res = await fetch(`${_base}/${path}`)
  if (!res.ok) throw new Error(`fetch failed: ${path} (${res.status})`)
  return res.text()
}

// Snapshots manifest lives at the root base regardless of the currently-
// selected snapshot; fetched directly so a selected snapshot does not
// hide the index of available snapshots.
export async function loadSnapshotsManifest() {
  const res = await fetch(`${DEFAULT_BASE}/snapshots_manifest.json`)
  if (!res.ok) throw new Error(`snapshots_manifest.json (${res.status})`)
  return res.json()
}

// Optional preview-only runtime-correction artifacts written by
// scripts/orchestrator.py:_run_correction_preview. Each loader silently
// returns null on 404 so the dashboard's RuntimeCorrectionCard
// can hide itself when the preview is not available for the current
// run / snapshot. These files are NOT on the strict contract schema.
async function _maybeJson(path) {
  try {
    const res = await fetch(`${_base}/${path}`)
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}
export async function loadRuntimeEvents()          { return _maybeJson('runtime_events.json') }
// Burst-prediction ablation evidence (tools/burst_ablation.py). Static across
// runs (not regenerated per RUN), so it loads optionally and the card hides
// itself when the file is absent.
export async function loadBurstAblation()          { return _maybeJson('burst_ablation.json') }
export async function loadCorrectionProposal()     { return _maybeJson('correction_proposal.json') }
export async function loadCorrectionGuardDecision(){ return _maybeJson('correction_guard_decision.json') }
export async function loadCorrectionApplied()      { return _maybeJson('correction_applied.json') }

// Returns { events: [...], errors: [...bad-line messages] }
// Events are normalized through the schema-compat layer (tick/algo spellings)
// using `defaultAlgo` when an event omits its own algo, then sorted by tick.
export function parseJsonl(text, defaultAlgo = null) {
  const events = []
  const errors = []
  for (const raw of text.split('\n')) {
    const l = raw.trim()
    if (!l) continue
    try {
      events.push(normalizeTraceEvent(JSON.parse(l), defaultAlgo))
    } catch (e) {
      errors.push(`Bad JSON line: ${l.slice(0, 60)}`)
    }
  }
  events.sort((a, b) => (getEventTick(a) ?? 0) - (getEventTick(b) ?? 0))
  return { events, errors }
}

export async function loadManifest()       { return fetchJson('manifest.json') }
export async function loadRecommendation() { return fetchJson('recommendation.json') }
export async function loadGuardDecision()  { return fetchJson('guard_decision.json') }
export async function loadWorkloadSummary(){ return fetchJson('workload_summary.json') }
export async function loadMetrics()        { return fetchJson('metrics.json') }

export async function loadTrace(algo) {
  const file = ALGO_FILE_MAP[algo]
  if (!file) throw new Error(`Unknown algo: ${algo}`)
  const text = await fetchText(file)
  const { events } = parseJsonl(text, algo)
  return events
}

// Returns { traces: {Algo: events[]}, traceErrors: {Algo: string} }
export async function loadAllTraces() {
  const traces = {}
  const traceErrors = {}
  await Promise.all(
    Object.entries(ALGO_FILE_MAP).map(async ([algo, file]) => {
      try {
        const text = await fetchText(file)
        const { events, errors } = parseJsonl(text, algo)
        traces[algo] = events
        if (errors.length > 0) traceErrors[algo] = errors.join('; ')
      } catch (err) {
        traces[algo] = []
        traceErrors[algo] = err.message
      }
    })
  )
  return { traces, traceErrors }
}
