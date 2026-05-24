export default function Card({ label, className = '', style = {}, children }) {
  return (
    <div className={`card ${className}`} style={style}>
      {label && <div className="card-label">{label}</div>}
      {children}
    </div>
  )
}
