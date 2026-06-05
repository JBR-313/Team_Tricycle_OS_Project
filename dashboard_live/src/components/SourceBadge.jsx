/**
 * SourceBadge — compact data-source honesty chip (Page-level goal §2).
 *
 * Tells the presenter/viewer where the CURRENT data came from so simulator
 * output is never mistaken for a real xv6 kernel run. The label is derived
 * from the live-data manifest (backend / mode / metadata_source), never
 * hardcoded. Keep it small — no long prose.
 *
 *   XV6 TRACE      — real xv6 kernel executed under QEMU (manifest.backend=xv6)
 *   SIMULATOR      — host-side scheduler simulator (development fallback)
 *   FALLBACK       — committed/bundled data, not a fresh run
 *   SNAPSHOT       — a pre-generated profile snapshot is selected
 *   UNKNOWN SOURCE — manifest did not declare a recognizable source
 */
export function deriveSource(manifest, { loadError = false, snapshot = false } = {}) {
  if (loadError) return { label: 'FALLBACK', kind: 'fallback' }
  if (snapshot) return { label: 'SNAPSHOT', kind: 'snapshot' }
  const mf = manifest || {}
  if (mf.mode === 'fallback') return { label: 'FALLBACK', kind: 'fallback' }
  const backend = mf.backend || (mf.mode === 'xv6-log' ? 'xv6' : mf.mode)
  const fixture = mf.metadata_source === 'demo_fallback'
  if (backend === 'xv6') return { label: 'XV6 TRACE', kind: 'xv6', fixture }
  if (backend === 'simulator') return { label: 'SIMULATOR', kind: 'sim', fixture }
  return { label: 'UNKNOWN SOURCE', kind: 'unknown' }
}

export default function SourceBadge({ manifest, loadError = false, snapshot = false }) {
  const { label, kind, fixture } = deriveSource(manifest, { loadError, snapshot })
  const title = fixture
    ? `${label} — recommendation metadata came from a committed demo fixture (no live LLM call)`
    : `Current data source: ${label}`
  return (
    <span className={`source-badge source-badge-${kind}`} title={title}>
      {label}{fixture ? ' ·fixture' : ''}
    </span>
  )
}
