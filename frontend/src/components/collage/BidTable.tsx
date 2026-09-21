import { Link } from 'react-router-dom'
import { exportBidsUrl } from '../../api/client'
import type { Bid, Widget } from '../../lib/types'

export default function BidTable({
  widget,
  onDismiss,
  onSave,
}: {
  widget: Widget
  onDismiss?: () => void
  onSave?: () => void
}) {
  const data = widget.data as { total?: number; bids?: Bid[]; filters?: object }
  const bids = data.bids || []

  const f = (data.filters || {}) as Record<string, unknown>
  const qs = new URLSearchParams()
  if (typeof f.q === 'string' && f.q) qs.set('q', f.q)
  if (typeof f.category === 'string' && f.category) qs.set('category', f.category)
  if (typeof f.status === 'string' && f.status) qs.set('status', f.status)
  const discoveryTo = `/discovery${qs.toString() ? `?${qs.toString()}` : ''}`

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
          <button className="btn ghost" onClick={() => (window.location.href = exportBidsUrl(data.filters || {}))}>
            Download CSV
          </button>
          <Link className="btn ghost" to={discoveryTo}>
            View in Discovery →
          </Link>
          {onDismiss && (
            <button className="btn ghost" onClick={onDismiss} aria-label="Dismiss">
              ×
            </button>
          )}
        </div>
      </div>
      <div className="tablewrap" style={{ maxHeight: 280, overflowY: 'auto' }}>
        <table className="data">
          <thead>
            <tr>
              <th>Bid</th>
              <th>Category</th>
              <th>Buyer</th>
              <th>Deadline</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {bids.map((b) => (
              <tr key={b.bid_number}>
                <td>
                  <Link className="mono" to={`/bid?bid_number=${encodeURIComponent(b.bid_number)}`}>
                    {b.bid_number}
                  </Link>
                </td>
                <td>{b.category_name || '—'}</td>
                <td>{b.department || b.ministry || '—'}</td>
                <td>{b.end_date ? b.end_date.slice(0, 10) : '—'}</td>
                <td>
                  <span className="badge">{b.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
