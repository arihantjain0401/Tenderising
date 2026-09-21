import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { exportBidsUrl, getFacets, searchBids } from '../api/client'
import { setDiscoveryContext } from '../state/context'
import type { Bid, Facets, SearchParams, SearchResult } from '../lib/types'

const PAGE_SIZE = 50

const STATUS_OPTIONS = [
  { value: 'ongoing', label: 'Active' },
  { value: 'closed', label: 'Closed' },
  { value: 'all', label: 'All' },
]

interface Filters {
  q: string
  status: string
  ministry: string
  department: string
  category: string
  is_high_value: boolean
  has_boq: boolean
  has_documents: boolean
  end_after: string
  end_before: string
}

const EMPTY_FILTERS: Filters = {
  q: '',
  status: 'ongoing',
  ministry: '',
  department: '',
  category: '',
  is_high_value: false,
  has_boq: false,
  has_documents: false,
  end_after: '',
  end_before: '',
}

export default function Discovery() {
  const navigate = useNavigate()
  const [urlParams] = useSearchParams()
  const [facets, setFacets] = useState<Facets | null>(null)
  const [filters, setFilters] = useState<Filters>(() => ({
    ...EMPTY_FILTERS,
    q: urlParams.get('q') || '',
    category: urlParams.get('category') || '',
    status: urlParams.get('status') || 'ongoing',
  }))
  const [result, setResult] = useState<SearchResult | null>(null)
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState('deadline')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getFacets()
      .then(setFacets)
      .catch(() => setFacets(null))
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    const params: SearchParams = {
      q: filters.q || undefined,
      status: filters.status,
      ministry: filters.ministry || undefined,
      department: filters.department || undefined,
      category: filters.category || undefined,
      is_high_value: filters.is_high_value || undefined,
      has_boq: filters.has_boq || undefined,
      has_documents: filters.has_documents || undefined,
      end_after: filters.end_after || undefined,
      end_before: filters.end_before || undefined,
      sort,
      sort_dir: sortDir,
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
    }
    searchBids(params)
      .then((r) => {
        if (!cancelled) setResult(r)
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [filters, page, sort, sortDir])

  const set = <K extends keyof Filters>(key: K, value: Filters[K]) => {
    setFilters((f) => ({ ...f, [key]: value }))
    setPage(1)
  }

  const toggleSort = (key: string) => {
    if (sort === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSort(key)
      setSortDir('asc')
    }
    setPage(1)
  }

  const clearFilters = () => {
    setFilters(EMPTY_FILTERS)
    setPage(1)
  }

  const activeChips: { key: keyof Filters; label: string }[] = []
  if (filters.status !== 'ongoing') {
    activeChips.push({ key: 'status', label: STATUS_OPTIONS.find((s) => s.value === filters.status)?.label || filters.status })
  }
  if (filters.ministry) activeChips.push({ key: 'ministry', label: `Ministry: ${filters.ministry}` })
  if (filters.department) activeChips.push({ key: 'department', label: `Dept: ${filters.department}` })
  if (filters.category) activeChips.push({ key: 'category', label: `Category: ${filters.category}` })
  if (filters.is_high_value) activeChips.push({ key: 'is_high_value', label: 'High value' })
  if (filters.has_boq) activeChips.push({ key: 'has_boq', label: 'Has BOQ' })
  if (filters.has_documents) activeChips.push({ key: 'has_documents', label: 'Has documents' })
  if (filters.end_after) activeChips.push({ key: 'end_after', label: `Closes ≥ ${filters.end_after}` })
  if (filters.end_before) activeChips.push({ key: 'end_before', label: `Closes ≤ ${filters.end_before}` })

  const totalPages = result ? Math.max(1, Math.ceil(result.total / PAGE_SIZE)) : 1

  const addToAsk = () => {
    if (!result || result.total === 0) return
    setDiscoveryContext({
      total: result.total,
      filters: {
        q: filters.q || undefined,
        status: filters.status,
        ministry: filters.ministry || undefined,
        department: filters.department || undefined,
        category: filters.category || undefined,
        is_high_value: filters.is_high_value || undefined,
        has_boq: filters.has_boq || undefined,
        has_documents: filters.has_documents || undefined,
        end_after: filters.end_after || undefined,
        end_before: filters.end_before || undefined,
      },
      bids: result.bids.map((b) => ({
        bid_number: b.bid_number,
        category_name: b.category_name,
        department: b.department,
        end_date: b.end_date,
        status: b.status,
      })),
    })
    navigate('/')
  }

  const downloadCsv = () => {
    window.location.href = exportBidsUrl({
      q: filters.q || undefined,
      status: filters.status,
      ministry: filters.ministry || undefined,
      department: filters.department || undefined,
      category: filters.category || undefined,
      is_high_value: filters.is_high_value || undefined,
      has_boq: filters.has_boq || undefined,
      has_documents: filters.has_documents || undefined,
      end_after: filters.end_after || undefined,
      end_before: filters.end_before || undefined,
    })
  }

  return (
    <div className="page">
      <div className="filters">
        <label className="label">
          Search
          <input
            className="input"
            placeholder="Bid number or category…"
            value={filters.q}
            onChange={(e) => set('q', e.target.value)}
          />
        </label>
        <label className="label">
          Status
          <select className="select" value={filters.status} onChange={(e) => set('status', e.target.value)}>
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="label">
          Ministry
          <select className="select" value={filters.ministry} onChange={(e) => set('ministry', e.target.value)}>
            <option value="">All</option>
            {(facets?.ministries || []).map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <label className="label">
          Department
          <select className="select" value={filters.department} onChange={(e) => set('department', e.target.value)}>
            <option value="">All</option>
            {(facets?.departments || []).map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <label className="label">
          Category
          <select className="select" value={filters.category} onChange={(e) => set('category', e.target.value)}>
            <option value="">All</option>
            {(facets?.categories || []).map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label className="label">
          Closes after
          <input
            className="input"
            type="date"
            value={filters.end_after}
            onChange={(e) => set('end_after', e.target.value)}
          />
        </label>
        <label className="label">
          Closes before
          <input
            className="input"
            type="date"
            value={filters.end_before}
            onChange={(e) => set('end_before', e.target.value)}
          />
        </label>
      </div>

      <div className="filter-actions">
        <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13 }}>
          <input
            type="checkbox"
            checked={filters.is_high_value}
            onChange={(e) => set('is_high_value', e.target.checked)}
          />
          High value
        </label>
        <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13 }}>
          <input type="checkbox" checked={filters.has_boq} onChange={(e) => set('has_boq', e.target.checked)} />
          Has BOQ
        </label>
        <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13 }}>
          <input
            type="checkbox"
            checked={filters.has_documents}
            onChange={(e) => set('has_documents', e.target.checked)}
          />
          Has documents
        </label>
        <span style={{ flex: 1 }} />
        <button className="btn ghost" onClick={clearFilters}>
          Clear
        </button>
        <button className="btn" onClick={downloadCsv}>
          Download CSV
        </button>
        <button className="btn primary" onClick={addToAsk} disabled={!result || result.total === 0}>
          Add {result ? result.total.toLocaleString() : 0} results to Ask context
        </button>
      </div>

      {(facets?.unavailable.length ?? 0) > 0 && (
        <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
          Not available yet: {facets?.unavailable.map((u) => u.toUpperCase()).join(', ')}
        </p>
      )}

      {activeChips.length > 0 && (
        <div className="chips-row">
          {activeChips.map((c) => (
            <span key={c.key} className="chip">
              {c.label}
              <button onClick={() => set(c.key, (EMPTY_FILTERS[c.key] as Filters[typeof c.key]))}>×</button>
            </span>
          ))}
        </div>
      )}

      <div className="filter-actions">
        <span className="result-count">{result ? `${result.total.toLocaleString()} bids` : '…'}</span>
        {loading && <span className="muted">loading…</span>}
        {error && <span style={{ color: 'var(--danger)' }}>{error}</span>}
      </div>

      {result && result.bids.length === 0 ? (
        <div className="empty">No bids match these filters.</div>
      ) : (
        <div className="tablewrap">
          <table className="data">
            <thead>
              <tr>
                <th>Bid number</th>
                <th className="sortable" onClick={() => toggleSort('category')}>
                  Category {sort === 'category' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                </th>
                <th>Buyer</th>
                <th className="sortable" onClick={() => toggleSort('deadline')}>
                  Deadline {sort === 'deadline' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                </th>
                <th className="sortable" onClick={() => toggleSort('status')}>
                  Status {sort === 'status' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                </th>
                <th>Qty</th>
                <th>Docs</th>
              </tr>
            </thead>
            <tbody>
              {(result?.bids || []).map((b: Bid) => (
                <tr key={b.bid_number}>
                  <td>
                    <Link className="mono" to={`/bid?bid_number=${encodeURIComponent(b.bid_number)}`}>
                      {b.bid_number}
                    </Link>
                  </td>
                  <td>{b.category_name || <span className="muted">—</span>}</td>
                  <td>{b.department || b.ministry || <span className="muted">—</span>}</td>
                  <td>{b.end_date ? b.end_date.slice(0, 10) : <span className="muted">—</span>}</td>
                  <td>
                    <span className="badge">{b.status}</span>
                  </td>
                  <td>{b.total_quantity || <span className="muted">—</span>}</td>
                  <td>
                    {b.has_boq ? 'BOQ' : ''}
                    {b.has_boq && b.has_documents ? ' · ' : ''}
                    {b.has_documents && !b.has_boq ? 'docs' : ''}
                    {!b.has_boq && !b.has_documents ? <span className="muted">—</span> : ''}
                    {b.is_high_value ? <span className="badge high" style={{ marginLeft: 6 }}>high</span> : ''}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="filter-actions" style={{ marginTop: 12 }}>
        <button className="btn" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
          ← Prev
        </button>
        <span className="muted">
          Page {page} / {totalPages}
        </span>
        <button className="btn" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
          Next →
        </button>
      </div>
    </div>
  )
}
