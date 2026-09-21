interface Row {
  key: string
  label: string
  count: number
}

export default function BarList({ rows }: { rows: Row[] }) {
  const max = Math.max(1, ...rows.map((r) => r.count))
  return (
    <div>
      {rows.map((r) => (
        <div key={r.key} className="bar-row">
          <span className="bar-label">{r.label}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(r.count / max) * 100}%` }} />
          </div>
          <span className="bar-value">{r.count}</span>
        </div>
      ))}
    </div>
  )
}
