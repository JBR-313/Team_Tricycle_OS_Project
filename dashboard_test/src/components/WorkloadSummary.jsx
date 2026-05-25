import Card from './Card.jsx'

export default function WorkloadSummary({ workloadSummary }) {
  const wl = workloadSummary || {}
  const n      = wl.process_count || 5
  const cpuR   = wl.cpu_bound_ratio
  const iaR    = wl.interactive_ratio
  const cpuCnt = cpuR != null ? Math.round(cpuR * n) : null
  const iaCnt  = iaR  != null ? Math.round(iaR  * n) : null
  const wlType = (wl.workload_type || 'mixed').replace(/_/g, ' ')
  const tgt    = (wl.target_metric || '').replace(/_/g, ' ')
  const sr     = wl.has_starvation_risk
  const risks  = wl.main_risks || []

  return (
    <Card label="Workload Summary" className="card-wl">
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '3px 3px', alignContent: 'flex-start', flex: 1, minHeight: 0 }}>
        <span className="pill" style={{ background: '#ede9fe', color: '#6d28d9', textTransform: 'capitalize' }}>{wlType}</span>
        <span className="pill" style={{ background: '#dbeafe', color: '#1d4ed8' }}>{n} procs</span>
        {tgt && <span className="pill" style={{ background: '#d1fae5', color: '#059669' }}>↳ {tgt}</span>}
        {cpuCnt != null && <span className="pill" style={{ background: '#f1f5f9', color: '#475569' }}>CPU {cpuCnt}p</span>}
        {iaCnt  != null && <span className="pill" style={{ background: '#f1f5f9', color: '#475569' }}>IA {iaCnt}p</span>}
        {risks.map(r => (
          <span key={r} className="pill" style={{ background: '#fef3c7', color: '#b45309', fontSize: '0.57rem' }}>
            ⚠ {r.replace(/_/g, ' ')}
          </span>
        ))}
        <span className="pill" style={{ background: sr ? '#fee2e2' : '#d1fae5', color: sr ? '#dc2626' : '#059669' }}>
          {sr ? '⚠ Starvation Risk' : '✓ No Starvation'}
        </span>
      </div>
    </Card>
  )
}
