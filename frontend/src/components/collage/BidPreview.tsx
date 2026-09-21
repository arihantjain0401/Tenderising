import { Link } from 'react-router-dom'
import type { BidDetail, Widget } from '../../lib/types'

export default function BidPreview({
  widget,
  onDismiss,
  onSave,
}: {
  widget: Widget
  onDismiss?: () => void
  onSave?: () => void
}) {
  const d = widget.data as unknown as BidDetail
  const buyer = [d.ministry, d.department, d.organisation, d.office].filter(Boolean).join(' → ')

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
      <p>
        <strong className="mono">{d.bid_number}</strong>{' '}
        <span className="badge" style={{ marginLeft: 6 }}>
          {d.status}
        </span>
      </p>
      <p>
        <strong>Category:</strong> {d.category_name || '—'}
      </p>
      <p>
        <strong>Buyer:</strong> {buyer || '—'}
      </p>
      <p>
        <strong>Deadline:</strong> {d.end_date ? d.end_date.slice(0, 10) : '—'}
      </p>
      <Link to={`/bid?bid_number=${encodeURIComponent(d.bid_number)}`}>Open tender →</Link>
    </div>
  )
}
