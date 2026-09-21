import type { DepartmentCount, Widget } from '../../lib/types'
import BarList from './BarList'

export default function BuyerBreakdown({
  widget,
  onDismiss,
  onSave,
}: {
  widget: Widget
  onDismiss?: () => void
  onSave?: () => void
}) {
  const departments = ((widget.data as { departments?: DepartmentCount[] }).departments || []).map(
    (d) => ({ key: d.department, label: d.department, count: d.count }),
  )

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
      {departments.length === 0 ? (
        <div className="muted">No buyer breakdown available.</div>
      ) : (
        <BarList rows={departments} />
      )}
    </div>
  )
}
