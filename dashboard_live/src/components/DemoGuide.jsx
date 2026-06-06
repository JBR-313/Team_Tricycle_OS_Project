import Card from './Card.jsx'

// Compact 5-step demo flow card. Static guidance only — does not
// read or mutate any pipeline data, does not modify layout. Sits as
// the first child of the left column so the audience has a labeled
// entry point on first paint, then disappears into the background
// once the presenter has walked the spine. See
// docs/dashboard_live_demo_readability_audit.md for the spec.
//
// Optional interaction (PR-level addition): clicking a step briefly
// outlines the matching element on screen so a presenter can point
// at it without losing the slide. Pure inline-style flash — no
// CSS change, no scroll-into-view, no layout shift.
const STEPS = [
  {
    label: 'Backend badge',
    text: 'Confirm the header reads "XV6 TRACE". That is the honesty signal — real xv6 trace data, not the simulator fallback.',
    selector: '.backend-badge',
  },
  {
    label: 'LLM pick',
    text: 'Top-left: the recommendation card shows the algorithm. The "Why this algorithm?" card below reads the LLM\'s own reason and the workload traits it cited.',
    selector: '.card-rec',
  },
  {
    label: 'Metric trade-off',
    text: 'The "Metric trade-off" card shows who would win on each metric. The current target metric row is highlighted — the LLM is honestly best there.',
    selector: '.card-cf',
  },
  {
    label: 'xv6 schedule',
    text: 'Center column: the Gantt and process lanes show the actual xv6 schedule that produced these metrics, tick by tick.',
    selector: '.card-gantt',
  },
  {
    label: 'Generality',
    text: 'The Metric trade-off card already ran all six algorithms on this workload — not just the recommended one. The same orchestrator pipeline also runs every curated xv6 profile (interactive / cpu_bound / mixed / priority_sensitive); re-run it with a different --workload to regenerate this view.',
    selector: '.card-cf',
  },
]

// Briefly outline an element matched by selector. Pure inline-style
// — no CSS class added, no DOM moved. Silently no-ops if the
// selector matches nothing (e.g. an element absent from the current layout).
function flashElement(selector) {
  const el = typeof document !== 'undefined'
    ? document.querySelector(selector)
    : null
  if (!el) return
  const prev = {
    outline: el.style.outline,
    outlineOffset: el.style.outlineOffset,
    transition: el.style.transition,
  }
  el.style.transition = 'outline-color 200ms ease-out'
  el.style.outline = '3px solid #7c3aed'
  el.style.outlineOffset = '4px'
  setTimeout(() => {
    el.style.outline = prev.outline || ''
    el.style.outlineOffset = prev.outlineOffset || ''
    el.style.transition = prev.transition || ''
  }, 1400)
}

export default function DemoGuide() {
  return (
    <Card label="Demo flow" className="card-demo-guide">
      <div style={{
        fontSize: '0.55rem', color: '#94a3b8', marginBottom: 4, flexShrink: 0,
      }}>
        Read these 5 cards / controls in order. Click a step to flash it on screen.
      </div>
      <ol style={{
        margin: 0, paddingLeft: 0, listStyle: 'none',
        display: 'flex', flexDirection: 'column', gap: 3,
        flex: 1, minHeight: 0, overflowY: 'auto',
      }}>
        {STEPS.map((s, i) => (
          <li key={s.label} style={{ display: 'flex', gap: 5, alignItems: 'flex-start' }}>
            <button
              type="button"
              onClick={() => flashElement(s.selector)}
              title={`Flash the ${s.label} on screen`}
              style={{
                display: 'inline-flex', justifyContent: 'center', alignItems: 'center',
                minWidth: 14, height: 14, borderRadius: '50%',
                background: '#ede9fe', color: '#6d28d9',
                fontSize: '0.55rem', fontWeight: 700,
                flexShrink: 0, marginTop: 1,
                border: 'none', padding: 0, cursor: 'pointer',
              }}
            >
              {i + 1}
            </button>
            <span style={{ fontSize: '0.58rem', lineHeight: 1.4 }}>
              <strong style={{ color: '#334155' }}>{s.label}.</strong>{' '}
              <span style={{ color: '#475569' }}>{s.text}</span>
            </span>
          </li>
        ))}
      </ol>
    </Card>
  )
}
