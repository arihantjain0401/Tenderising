import type { Widget, WidgetKind } from '../lib/types'

const WIDE: Record<WidgetKind, boolean> = {
  bid_table: true,
  summary_cards: true,
  deadline_chart: false,
  buyer_breakdown: false,
  bid_preview: true,
}

export function isWide(kind: WidgetKind): boolean {
  return WIDE[kind] ?? false
}

export function upsertWidget(list: Widget[], widget: Widget): Widget[] {
  const next = list.filter((w) => w.id !== widget.id)
  return [...next, widget]
}

export function removeWidget(list: Widget[], id: string): Widget[] {
  return list.filter((w) => w.id !== id)
}
