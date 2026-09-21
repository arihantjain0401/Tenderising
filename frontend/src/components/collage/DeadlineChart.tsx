import type { DeadlineBucket, Widget } from '../../lib/types'
import BarList from './BarList'

const LABELS: Record<string, string> = {
  overdue: 'Overdue',
  this_week: 'This week',
  next_30d: 'Next 30 days',
  '30_90d': '30–90 days',
  '90d_plus': '90+ days',
  no_date: 'No date',
}

export default function DeadlineChart({
  widget,
  onDismiss,
  onSave,
}: {
  widget: Widget
  onDismiss?: () => void
  onSave?: () => void
}) {
  const buckets = ((widget.data as { buckets?: DeadlineBucket[] }).buckets || []).filter(
    (b) => b.count > 0,
  )
  const rows = buckets.map((b) => ({
    key: b.bucket,
    label: LABELS[b.bucket] || b.bucket,
    count: b.count,
  }))

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
      {rows.length === 0 ? <div className="muted">No upcoming deadlines.</div> : <BarList rows={rows} />}
    </div>
  )
}
