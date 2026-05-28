/**
 * Run-server HTTP client (matches scripts/run_server.py).
 * Configurable base via env: VITE_RUN_API (default http://127.0.0.1:8765).
 * If the server is unreachable, callers should fall back to a clear error UI
 * rather than crash — see docs/dashboard_run_button_design.md §6.
 */
const BASE = (import.meta.env?.VITE_RUN_API || 'http://127.0.0.1:8765').replace(/\/+$/, '')

export async function healthCheck() {
  try {
    const r = await fetch(`${BASE}/api/health`)
    if (!r.ok) return { ok: false, error: `HTTP ${r.status}` }
    return await r.json()
  } catch (err) {
    return { ok: false, error: err.message }
  }
}

export async function getStatus() {
  const r = await fetch(`${BASE}/api/status`)
  if (!r.ok) throw new Error(`status HTTP ${r.status}`)
  return await r.json()
}

export async function startRun(params) {
  const r = await fetch(`${BASE}/api/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) {
    const reason = data?.error || `HTTP ${r.status}`
    throw new Error(reason)
  }
  return data
}
