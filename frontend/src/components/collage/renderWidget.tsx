import type { Widget } from '../../lib/types'
import BidTable from './BidTable'
import SummaryCards from './SummaryCards'
import DeadlineChart from './DeadlineChart'
import BuyerBreakdown from './BuyerBreakdown'
import BidPreview from './BidPreview'

export function renderWidget(
  w: Widget,
  onDismiss?: () => void,
  onSave?: () => void,
) {
  switch (w.kind) {
    case 'bid_table':
      return <BidTable widget={w} onDismiss={onDismiss} onSave={onSave} />
    case 'summary_cards':
      return <SummaryCards widget={w} onDismiss={onDismiss} onSave={onSave} />
    case 'deadline_chart':
      return <DeadlineChart widget={w} onDismiss={onDismiss} onSave={onSave} />
    case 'buyer_breakdown':
      return <BuyerBreakdown widget={w} onDismiss={onDismiss} onSave={onSave} />
    case 'bid_preview':
      return <BidPreview widget={w} onDismiss={onDismiss} onSave={onSave} />
    default:
      return null
  }
}
