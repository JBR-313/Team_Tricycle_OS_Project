import Card from './Card.jsx'

// Compact 5-step demo flow card. Static guidance only — does not
// read or mutate any pipeline data, does not modify layout. Sits as
// the first child of the left column so the audience has a labeled
// entry point on first paint, then disappears into the background
// once the presenter has walked the spine. See
// docs/dashboard_live_demo_readability_audit.md for the spec.
const STEPS = [
  {
    label: 'Backend badge',
    text: 'Confirm the header reads "XV6 TRACE". That is the honesty signal — real xv6 trace data, not the simulator fallback.',
  },
  {
    label: 'LLM pick',
    text: 'Top-left: the recommendation card shows the algorithm. The "Why this algorithm?" card below reads the LLM\'s own reason and the workload traits it cited.',
  },
  {
    label: 'Metric trade-off',
    text: 'The "Metric trade-off" card shows who would win on each metric. The current target metric row is highlighted — the LLM is honestly best there.',
  },
  {
    label: 'xv6 schedule',
    text: 'Center column: the Gantt and process lanes show the actual xv6 schedule that produced these metrics, tick by tick.',
  },
  {
    label: 'Generality',
    text: 'Switch the Snapshot selector in the header (interactive / cpu_bound / mixed / priority_sensitive) to prove the pipeline runs across every curated workload.',
  },
]

export default function DemoGuide() {
  return (
    <Card label="Demo flow" className="card-demo-guide">
      <div style={{
        fontSize: '0.55rem', color: '#94a3b8', marginBottom: 4, flexShrink: 0,
      }}>
        Read these 5 cards / controls in order during the demo.
      </div>
      <ol style={{
        margin: 0, paddingLeft: 0, listStyle: 'none',
        display: 'flex', flexDirection: 'column', gap: 3,
        flex: 1, minHeight: 0, overflowY: 'auto',
      }}>
        {STEPS.map((s, i) => (
          <li key={s.label} style={{ display: 'flex', gap: 5, alignItems: 'flex-start' }}>
            <span style={{
              display: 'inline-flex', justifyContent: 'center', alignItems: 'center',
              minWidth: 14, height: 14, borderRadius: '50%',
              background: '#ede9fe', color: '#6d28d9',
              fontSize: '0.55rem', fontWeight: 700,
              flexShrink: 0, marginTop: 1,
            }}>
              {i + 1}
            </span>
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
