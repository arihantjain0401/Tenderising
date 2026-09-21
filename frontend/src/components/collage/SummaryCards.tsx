import type { Widget } from '../../lib/types'

interface Card {
  label: string
  value: string
}

export default function SummaryCards({
  widget,
  onDismiss,
  onSave,
}: {
  widget: Widget
  onDismiss?: () => void
  onSave?: () => void
}) {
  const d = widget.data
  const cards: Card[] = []
  const num = (v: unknown) => (typeof v === 'number' ? v.toLocaleString() : String(v ?? '—'))

  if (typeof d.total === 'number') cards.push({ label: 'Matching bids', value: num(d.total) })
  if (typeof d.high_value === 'number') cards.push({ label: 'High value', value: num(d.high_value) })
  if (typeof d.with_boq === 'number') cards.push({ label: 'With BOQ', value: num(d.with_boq) })
  if (typeof d.closing_7d === 'number')
    cards.push({ label: 'Closing in 7 days', value: num(d.closing_7d) })
  if (typeof d.total_bids === 'number') cards.push({ label: 'Total bids', value: num(d.total_bids) })
  if (typeof d.active_bids === 'number') cards.push({ label: 'Active bids', value: num(d.active_bids) })

  if (cards.length === 0) return null

  return (
    <div className="widget">
      <div className="widget-head">
        <h3 className="widget-title">{widget.title}</h3>
        <div className="widget-actions">
          {onSave && (
            <button className="btn ghost" onClick={onSave}>
              Save to workspace
            </button>
          )}
          {onDismiss && (
            <button className="btn ghost" onClick={onDismiss} aria-label="Dismiss">
              ×
            </button>
          )}
        </div>
      </div>
      <div className="stat-row">
        {cards.map((c) => (
          <div key={c.label} className="stat">
            <div className="stat-value">{c.value}</div>
            <div className="stat-label">{c.label}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
