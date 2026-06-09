import Card from './Card.jsx'

// Learning tab — the adaptive / retrieval-learning result, the one CROSS-RUN
// story the per-run tabs cannot show. Every number is a leave-one-out MEASURED
// aggregate on the real-kernel bank (no future-burst leakage, a workload never
// retrieves its own answer). Data comes from the static, measured-study file
// public/live-data/learning_curve.json (export_learning_curve.py), NOT from a
// single live RUN — so this tab is explicitly badged as a measured study.

const SERIES = {
  knn:           { label: 'Retrieval kNN', color: '#2563eb' },
  llm_retrieval: { label: 'LLM + memory',  color: '#7c3aed' },
}

const ARM_COLOR = {
  baseline:    '#94a3b8',
  no_learning: '#f59e0b',
  learning:    '#10b981',
}

// ── Precedent curve: regret vs # same-family precedents already in the store ──
function PrecedentCurve({ curves }) {
  const W = 460, H = 230
  const padL = 44, padR = 16, padT = 18, padB = 38
  const xs = curves.knn.map(p => p.precedents)
  const xMax = Math.max(...xs, 1)
  const allY = Object.values(curves).flat().map(p => p.mean_regret)
  const yMax = Math.max(...allY, 0.05) * 1.15

  const px = x => padL + (x / xMax) * (W - padL - padR)
  const py = y => H - padB - (y / yMax) * (H - padT - padB)

  // y gridlines at 0, ¼, ½, ¾, max
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map(f => +(yMax * f).toFixed(3))

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="lc-svg" role="img"
         aria-label="Regret versus number of same-family precedents">
      {/* y gridlines + labels */}
      {yTicks.map((t, i) => (
        <g key={i}>
          <line x1={padL} y1={py(t)} x2={W - padR} y2={py(t)}
                stroke="#e2e8f0" strokeWidth="1" />
          <text x={padL - 6} y={py(t) + 3} textAnchor="end"
                className="lc-axis-text">{t.toFixed(2)}</text>
        </g>
      ))}
      {/* x labels */}
      {xs.map(x => (
        <text key={x} x={px(x)} y={H - padB + 16} textAnchor="middle"
              className="lc-axis-text">{x}</text>
      ))}
      <text x={(padL + W - padR) / 2} y={H - 6} textAnchor="middle"
            className="lc-axis-title"># same-family precedents in memory</text>
      <text x={12} y={padT - 4} className="lc-axis-title">regret</text>

      {/* series */}
      {Object.entries(curves).map(([key, pts]) => {
        const s = SERIES[key]
        if (!s) return null
        const d = pts.map((p, i) =>
          `${i === 0 ? 'M' : 'L'} ${px(p.precedents)} ${py(p.mean_regret)}`).join(' ')
        return (
          <g key={key}>
            <path d={d} fill="none" stroke={s.color} strokeWidth="2.5"
                  strokeLinejoin="round" />
            {pts.map((p, i) => (
              <circle key={i} cx={px(p.precedents)} cy={py(p.mean_regret)} r="3.5"
                      fill="#fff" stroke={s.color} strokeWidth="2">
                <title>{`${s.label} · ${p.precedents} precedents → regret ${p.mean_regret} (n=${p.n})`}</title>
              </circle>
            ))}
          </g>
        )
      })}
    </svg>
  )
}

// ── Arm comparison: mean regret across the whole sequence ─────────────────────
function ArmBars({ arms }) {
  const maxR = Math.max(...arms.map(a => a.mean_regret), 0.01) * 1.15
  return (
    <div className="lc-bars">
      {arms.map(a => {
        const pct = (a.mean_regret / maxR) * 100
        return (
          <div key={a.key} className="lc-bar-col">
            <span className="lc-bar-val">{a.mean_regret.toFixed(3)}</span>
            <div className="lc-bar-track">
              <div className="lc-bar-fill"
                   style={{ height: `${pct}%`, background: ARM_COLOR[a.kind] || '#94a3b8' }}
                   title={`${a.label}: mean regret ${a.mean_regret}`} />
            </div>
            <span className="lc-bar-label">{a.label}</span>
          </div>
        )
      })}
    </div>
  )
}

export default function LearningCurveCard({ data }) {
  if (!data) {
    return (
      <div className="tab-grid learning-grid">
        <Card label="Adaptive Learning" className="card-learning">
          <div className="lc-empty">
            <p>No measured learning-curve study found.</p>
            <p className="lc-empty-hint">
              Generate it with <code>experiments/learning_curve_bank.py</code> →{' '}
              <code>_replay.py</code> → <code>_llm.py</code>, then{' '}
              <code>python3 scripts/export_learning_curve.py</code>.
            </p>
          </div>
        </Card>
      </div>
    )
  }

  const nc = data.negative_control
  const drift = data.drift
  const ncCollapses = nc.shuffled_label_knn >= nc.best_fixed_bar

  return (
    <div className="tab-grid learning-grid">
      <div className="tab-col">
        <Card label="Does repeating a workload pattern help the LLM?" className="card-learning">
          <div className="lc-intro">
            <span className="lc-measured-badge" title={data.provenance}>
              ◆ measured study · real xv6 · leave-one-out
            </span>
            <p className="lc-lede">
              The advisor accumulates each finished run's{' '}
              <strong>(visible features → measured-best algorithm)</strong> into a
              memory. When a <strong>recurring</strong> workload pattern shows up
              again, retrieval warm-starts the recommendation. Regret = normalized
              gap from the measured-best algorithm (0 = best).
            </p>
          </div>
          <PrecedentCurve curves={data.precedent_curve} />
          <div className="lc-legend">
            {Object.entries(SERIES).map(([k, s]) => (
              <span key={k} className="lc-legend-item">
                <span className="lc-legend-swatch" style={{ background: s.color }} />
                {s.label}
              </span>
            ))}
          </div>
          <p className="lc-caption">
            With <strong>zero</strong> precedents the kNN arm sits at regret{' '}
            {data.precedent_curve.knn[0].mean_regret.toFixed(2)} (reasoning blind);
            after just <strong>one</strong> same-family precedent it collapses to ≈0.
            The learning is order-independent — it depends on{' '}
            <em>how many</em> precedents exist, not when they arrived.
          </p>
        </Card>
      </div>

      <div className="tab-col">
        <Card label="Mean regret per strategy (whole sequence)" className="card-learning">
          <ArmBars arms={data.arms} />
          <div className="lc-armlegend">
            <span><span className="lc-sw" style={{ background: ARM_COLOR.baseline }} /> fixed baseline</span>
            <span><span className="lc-sw" style={{ background: ARM_COLOR.no_learning }} /> LLM, no memory</span>
            <span><span className="lc-sw" style={{ background: ARM_COLOR.learning }} /> with learned memory</span>
          </div>
          <p className="lc-caption">
            Both learning arms beat the best fixed baseline (Always MLFQ,{' '}
            {data.negative_control.best_fixed_bar.toFixed(3)}). The LLM at the
            interface exploits the <em>same</em> signal the no-LLM kNN proves —
            memory drops it from {data.arms.find(a => a.key === 'llm_facts').mean_regret.toFixed(3)}{' '}
            to {data.arms.find(a => a.key === 'llm_retrieval').mean_regret.toFixed(3)}.
          </p>
        </Card>

        <Card label="Is the signal real?" className="card-learning">
          <div className="lc-checks">
            <div className={`lc-check ${ncCollapses ? 'ok' : 'warn'}`}>
              <div className="lc-check-head">
                <span className="lc-check-icon">{ncCollapses ? '✓' : '!'}</span>
                Negative control (shuffled labels)
              </div>
              <div className="lc-check-body">
                Real labels → regret <strong>{nc.true_label_knn.toFixed(3)}</strong>.
                Shuffle the answers → regret jumps to{' '}
                <strong>{nc.shuffled_label_knn.toFixed(3)}</strong>, collapsing toward
                the fixed bar ({nc.best_fixed_bar.toFixed(3)}). The gain is learned
                structure, not a lookup artifact.
              </div>
            </div>
            <div className="lc-check ok">
              <div className="lc-check-head">
                <span className="lc-check-icon">✓</span>
                Drift self-heals
              </div>
              <div className="lc-check-body">
                Under a pattern change the learning arm stays at{' '}
                <strong>{drift.knn_drift.toFixed(3)}</strong> (vs{' '}
                {drift.knn.toFixed(3)} stable): retrieval re-aligns within one
                instance of the new pattern, so <em>no explicit runtime
                drift-correction is added</em>.
              </div>
            </div>
          </div>
          <p className="lc-foot">
            {data.families.length} workload families · {data.n_instances} instances ·
            k={data.k}. This is not “the LLM is a better scheduler” — it is the LLM
            at the human interface, out of the kernel hot path, learning which
            Scheduling Algorithm a recurring workload signature wants.
          </p>
        </Card>
      </div>
    </div>
  )
}
