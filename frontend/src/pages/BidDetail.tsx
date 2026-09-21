import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { getBidDetail, saveTender, fetchDocuments } from '../api/client'
import { setDiscoveryContext } from '../state/context'
import type { BidDetail } from '../lib/types'

type Tab = 'overview' | 'documents' | 'boq' | 'requirements' | 'corrigenda' | 'history'

const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'documents', label: 'Documents' },
  { id: 'boq', label: 'BOQ' },
  { id: 'requirements', label: 'Requirements' },
  { id: 'corrigenda', label: 'Corrigenda' },
  { id: 'history', label: 'History' },
]

function fmt(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'number') return v.toLocaleString('en-IN')
  const n = Number(v)
  return Number.isFinite(n) ? n.toLocaleString('en-IN') : String(v)
}

export default function BidDetail() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const bidNumber = params.get('bid_number') || ''
  const [detail, setDetail] = useState<BidDetail | null>(null)
  const [tab, setTab] = useState<Tab>('overview')
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [fetchingDocs, setFetchingDocs] = useState(false)
  const [docMessage, setDocMessage] = useState<string | null>(null)

  useEffect(() => {
    if (!bidNumber) return
    let cancelled = false
    setDetail(null)
    setError(null)
    getBidDetail(bidNumber)
      .then((d) => {
        if (!cancelled) setDetail(d)
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [bidNumber])

  const addToAsk = () => {
    if (!detail) return
    setDiscoveryContext({
      total: 1,
      filters: {},
      bids: [
        {
          bid_number: detail.bid_number,
          category_name: detail.category_name,
          department: detail.department,
          end_date: detail.end_date,
          status: detail.status,
        },
      ],
    })
    navigate('/')
  }

  const onSave = async () => {
    if (!detail) return
    try {
      await saveTender(detail.bid_number)
      setSaved(true)
      setSaveError(null)
    } catch (e) {
      if (String(e).includes('401')) {
        window.location.href = '/api/auth/login'
      } else {
        setSaveError(String(e))
      }
    }
  }

  const onGetDoc = async () => {
    if (!detail) return
    setFetchingDocs(true)
    setDocMessage(null)
    try {
      const r = await fetchDocuments(detail.bid_number)
      setDocMessage(
        r.fetched
          ? `Fetched ${r.documents.length} document(s) from GeM.`
          : r.documents.length > 0
            ? 'Documents already available in our database.'
            : r.error || 'No documents found.',
      )
      setDetail(await getBidDetail(detail.bid_number))
    } catch (e) {
      setDocMessage(`Error: ${String(e)}`)
    } finally {
      setFetchingDocs(false)
    }
  }

  if (!bidNumber) return <div className="page">No bid selected.</div>
  if (error) return <div className="page">Error: {error}</div>
  if (!detail) return <div className="page muted">Loading…</div>

  const buyer = [detail.ministry, detail.department, detail.organisation, detail.office]
    .filter(Boolean)
    .join(' → ')

  return (
    <div className="page">
      <p className="muted" style={{ marginTop: 0 }}>
        <Link to="/discovery">← Discovery</Link>
      </p>

      <div className="detail-header">
        <h1 className="detail-title">{detail.bid_number}</h1>
        <span className="badge">{detail.status}</span>
        {detail.is_high_value && (
          <span className="badge high" style={{ marginLeft: 6 }}>
            high value
          </span>
        )}

        <div className="detail-meta">
          <div>
            <div className="k">Buyer</div>
            <div className="v">{buyer || '—'}</div>
          </div>
          <div>
            <div className="k">Category</div>
            <div className="v">{detail.category_name || '—'}</div>
          </div>
          <div>
            <div className="k">Value</div>
            <div className="v muted">Not available yet</div>
          </div>
          <div>
            <div className="k">EMD</div>
            <div className="v muted">Not available yet</div>
          </div>
          <div>
            <div className="k">Location</div>
            <div className="v muted">Not available yet</div>
          </div>
          <div>
            <div className="k">Deadline</div>
            <div className="v">{detail.end_date ? detail.end_date.slice(0, 16).replace('T', ' ') : '—'}</div>
          </div>
          <div>
            <div className="k">Quantity</div>
            <div className="v">{fmt(detail.total_quantity)}</div>
          </div>
          <div>
            <div className="k">Source</div>
            <div className="v">GeM</div>
          </div>
          <div>
            <div className="k">Last verified</div>
            <div className="v">{detail.last_verified ? detail.last_verified.slice(0, 10) : '—'}</div>
          </div>
        </div>

        <div className="detail-actions">
          <button className="btn" onClick={onSave} disabled={saved}>
            {saved ? 'Saved' : 'Save'}
          </button>
          <button className="btn primary" onClick={addToAsk}>
            Add to Ask context
          </button>
        </div>
        {saveError && <p style={{ color: 'var(--danger)' }}>{saveError}</p>}
      </div>

      <div className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`tab${tab === t.id ? ' active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <TabPanel tab={tab} detail={detail} onGetDoc={onGetDoc} fetchingDocs={fetchingDocs} docMessage={docMessage} />
    </div>
  )
}

function TabPanel({
  tab,
  detail,
  onGetDoc,
  fetchingDocs,
  docMessage,
}: {
  tab: Tab
  detail: BidDetail
  onGetDoc: () => void
  fetchingDocs: boolean
  docMessage: string | null
}) {
  switch (tab) {
    case 'overview':
      return (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>Overview</h3>
          <p>
            <strong>Bid number:</strong> <span className="mono">{detail.bid_number}</span>
          </p>
          <p>
            <strong>Status:</strong> {detail.status}
          </p>
          <p>
            <strong>Category:</strong> {detail.category_name || '—'}
          </p>
          <p>
            <strong>Start / end:</strong>{' '}
            {detail.start_date ? detail.start_date.slice(0, 10) : '—'} →{' '}
            {detail.end_date ? detail.end_date.slice(0, 10) : '—'}
          </p>
          <p>
            <strong>Quantity:</strong> {fmt(detail.total_quantity)}
          </p>
        </div>
      )
    case 'documents':
      return (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>Documents</h3>
          <div className="filter-actions">
            <button className="btn primary" onClick={onGetDoc} disabled={fetchingDocs}>
              {fetchingDocs ? 'Fetching…' : 'Get doc'}
            </button>
            <span className="muted" style={{ fontSize: 13 }}>
              Fetches documents from GeM if not already in our database.
            </span>
          </div>
          {docMessage && <p className="muted">{docMessage}</p>}
          {detail.documents.length === 0 ? (
            <div className="empty">No documents available for this bid.</div>
          ) : (
            <div className="tablewrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Title</th>
                    <th>Pages</th>
                    <th>Size</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {detail.documents.map((d) => (
                    <tr key={d.id}>
                      <td>{d.doc_type || '—'}</td>
                      <td>{d.title || '—'}</td>
                      <td>{d.page_count ?? '—'}</td>
                      <td>{d.byte_size ? `${Math.round(d.byte_size / 1024)} KB` : '—'}</td>
                      <td>
                        {d.download_url && (
                          <a href={d.download_url} target="_blank" rel="noreferrer">
                            Download
                          </a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )
    case 'boq':
      return (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>BOQ — line items</h3>
          {detail.line_items.length === 0 ? (
            <div className="empty">No BOQ line items available for this bid.</div>
          ) : (
            <div className="tablewrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Description</th>
                    <th>Qty</th>
                    <th>Unit</th>
                    <th>Consignee</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.line_items.map((it, i) => (
                    <tr key={i}>
                      <td>{it.item_no || '—'}</td>
                      <td>{it.description || '—'}</td>
                      <td>{fmt(it.quantity)}</td>
                      <td>{it.unit || '—'}</td>
                      <td>{it.consignee || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )
    case 'requirements':
      return (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>Participation</h3>
          {detail.participation.length === 0 ? (
            <div className="empty">No participation recorded for this bid.</div>
          ) : (
            <div className="tablewrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Stage</th>
                    <th>Seller</th>
                    <th>Result</th>
                    <th>Price</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.participation.map((p, i) => (
                    <tr key={i}>
                      <td>{p.stage || '—'}</td>
                      <td>{p.firm_name || '—'}</td>
                      <td>{p.result || '—'}</td>
                      <td>{fmt(p.total_price)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <h3>Award</h3>
          {detail.award ? (
            <p>
              {detail.award.l1_seller_name ? `L1: ${detail.award.l1_seller_name}` : 'Awarded'} ·{' '}
              {detail.award.awarded_value != null ? `₹${fmt(detail.award.awarded_value)}` : ''}
            </p>
          ) : (
            <div className="empty">No award recorded for this bid.</div>
          )}
        </div>
      )
    case 'corrigenda':
      return (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>Corrigenda</h3>
          {detail.corrigenda.length === 0 ? (
            <div className="empty">No corrigenda for this bid.</div>
          ) : (
            detail.corrigenda.map((c, i) => (
              <div key={i} style={{ marginBottom: 16 }}>
                <strong>{c.corrigendum_no || `Corrigendum ${i + 1}`}</strong>{' '}
                <span className="muted">{c.issue_date ? c.issue_date.slice(0, 10) : ''}</span>
                <p>{c.summary || '—'}</p>
              </div>
            ))
          )}
        </div>
      )
    case 'history':
      return (
        <div className="panel">
          <h3 style={{ marginTop: 0 }}>History</h3>
          <div className="empty">No change history recorded for this bid.</div>
        </div>
      )
  }
}
