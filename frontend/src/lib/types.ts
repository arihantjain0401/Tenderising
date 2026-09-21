export interface Bid {
  bid_number: string
  category_name: string | null
  status: string
  is_high_value: boolean | null
  total_quantity: string | null
  start_date: string | null
  end_date: string | null
  ministry: string | null
  department: string | null
  organisation: string | null
  office: string | null
  last_verified: string | null
  has_boq: boolean
  has_documents: boolean
}

export interface SearchResult {
  total: number
  limit: number
  offset: number
  bids: Bid[]
}

export interface Facets {
  ministries: string[]
  departments: string[]
  categories: string[]
  statuses: string[]
  unavailable: string[]
}

export interface SearchParams {
  q?: string
  status?: string
  ministry?: string
  department?: string
  category?: string
  is_high_value?: boolean
  has_boq?: boolean
  has_documents?: boolean
  end_after?: string
  end_before?: string
  sort?: string
  sort_dir?: string
  limit?: number
  offset?: number
}

export interface DiscoveryContextBid {
  bid_number: string
  category_name: string | null
  department: string | null
  end_date: string | null
  status: string
}

export interface DiscoveryContext {
  total: number
  filters: SearchParams
  bids: DiscoveryContextBid[]
}

export interface BidDocument {
  id: number
  doc_type: string | null
  title: string | null
  page_count: number | null
  byte_size: number | null
  content_type: string | null
  disclosure_state: string | null
  download_url: string | null
}

export interface Corrigendum {
  corrigendum_no: string | null
  issue_date: string | null
  summary: string | null
}

export interface LineItem {
  item_no: string | null
  description: string | null
  quantity: number | string | null
  unit: string | null
  unit_price: number | string | null
  total_price: number | string | null
  consignee: string | null
}

export interface ParticipationRow {
  stage: string | null
  firm_name: string | null
  result: string | null
  total_price: number | string | null
}

export interface Award {
  source: string | null
  awarded_value: number | string | null
  award_date: string | null
  l1_seller_name: string | null
  status: string | null
}

export interface BidDetail {
  bid_number: string
  category_name: string | null
  status: string
  is_high_value: boolean | null
  total_quantity: string | null
  start_date: string | null
  end_date: string | null
  ministry: string | null
  department: string | null
  organisation: string | null
  office: string | null
  last_verified: string | null
  corrigenda: Corrigendum[]
  documents: BidDocument[]
  line_items: LineItem[]
  participation: ParticipationRow[]
  award: Award | null
}

export type WidgetKind =
  | 'bid_table'
  | 'summary_cards'
  | 'deadline_chart'
  | 'buyer_breakdown'
  | 'bid_preview'

export interface Widget {
  id: string
  kind: WidgetKind
  title: string
  data: Record<string, unknown>
}

export interface DeadlineBucket {
  bucket: string
  count: number
}

export interface DepartmentCount {
  department: string
  count: number
}

export interface MeResponse {
  authenticated: boolean
  user?: { id: number; name: string | null; email: string; picture: string | null }
}

export interface SavedTenderItem {
  id: number
  bid_number: string
  snapshot: unknown
  note: string | null
  created_at: string | null
}

export interface SavedViewItem {
  id: number
  name: string
  filters: unknown
}

export interface NoteItem {
  id: number
  bid_number: string | null
  title: string | null
  body: string | null
  tags: string[]
  updated_at: string | null
}

export interface TagItem {
  id: number
  name: string
  color: string | null
}

export interface AlertItem {
  id: number
  name: string
  filters: unknown
  frequency: string | null
  enabled: boolean
}

export interface PipelineItemRow {
  id: number
  bid_number: string
  note: string | null
  position: number
}

export interface PipelineBoard {
  stages: string[]
  board: Record<string, PipelineItemRow[]>
}

export interface CalendarEventItem {
  id: number
  title: string
  description: string | null
  event_type: string | null
  starts_at: string | null
  ends_at: string | null
}

export interface Profile {
  user: { id: number; name: string | null; email: string; picture: string | null }
  preferences: {
    timezone: string | null
    default_view: string | null
    notification_prefs: unknown
  }
}
