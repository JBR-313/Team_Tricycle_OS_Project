import { normalizeTraceEvent, getEventTick } from './schemaCompat.js'

const BASE = '/live-data'

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
  const res = await fetch(`${BASE}/${path}`)
  if (!res.ok) throw new Error(`fetch failed: ${path} (${res.status})`)
  return res.json()
}

async function fetchText(path) {
  const res = await fetch(`${BASE}/${path}`)
  if (!res.ok) throw new Error(`fetch failed: ${path} (${res.status})`)
  return res.text()
}

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
