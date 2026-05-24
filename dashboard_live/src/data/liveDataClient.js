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

export function parseJsonl(text) {
  return text
    .split('\n')
    .map(l => l.trim())
    .filter(l => l.length > 0)
    .map(l => JSON.parse(l))
    .sort((a, b) => a.tick - b.tick)
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
  return parseJsonl(text)
}

export async function loadAllTraces() {
  const results = {}
  await Promise.all(
    Object.entries(ALGO_FILE_MAP).map(async ([algo, file]) => {
      try {
        const text = await fetchText(file)
        results[algo] = parseJsonl(text)
      } catch {
        results[algo] = []
      }
    })
  )
  return results
}
