import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  addToPipeline,
  createAlert,
  createNote,
  deleteChatSession,
  getMe,
  listAlerts,
  listChatSessions,
  listNotes,
  listPipeline,
  listSavedTenders,
  listSavedWidgets,
  listTags,
  logout,
  movePipeline,
  removeAlert,
  removeNote,
  removePipeline,
  removeSavedTender,
  removeSavedWidget,
  saveTender,
} from '../api/client'
import type { ChatSessionSummary, SavedWidgetItem } from '../api/client'
import type {
  AlertItem,
  MeResponse,
  NoteItem,
  PipelineBoard,
  SavedTenderItem,
  WidgetKind,
} from '../lib/types'
import { isWide } from '../state/collage'
import { renderWidget } from '../components/collage/renderWidget'

type Tab = 'saved' | 'notes' | 'alerts' | 'pipeline' | 'chats' | 'widgets' | 'profile'

const TABS: { id: Tab; label: string }[] = [
  { id: 'saved', label: 'Saved tenders' },
  { id: 'notes', label: 'Notes' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'pipeline', label: 'Pipeline' },
  { id: 'chats', label: 'Chats' },
  { id: 'widgets', label: 'Saved widgets' },
  { id: 'profile', label: 'Profile' },
]

export default function Workspace() {
  const [params] = useSearchParams()
  const [me, setMe] = useState<MeResponse | null>(null)
  const [tab, setTab] = useState<Tab>(() => {
    const t = params.get('tab') as Tab | null
    return t && TABS.some((x) => x.id === t) ? t : 'saved'
  })
  const [premium, setPremium] = useState(false)

  useEffect(() => {
    getMe()
      .then(setMe)
      .catch(() => setMe({ authenticated: false }))
  }, [])

  if (me === null) return <div className="page muted">Loading…</div>

  if (!me.authenticated) {
    return (
      <div className="page">
        <div className="signin-card">
          <h1>Workspace</h1>
          <p className="muted">Sign in to save tenders, take notes, set alerts, and track your pipeline.</p>
          <a className="btn primary" href="/api/auth/login">
            Sign in with Google
          </a>
          <p className="muted" style={{ fontSize: 13 }}>
            Your saved items are private to your account.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="page">
      <div className="workspace-head">
        <div>
          <h1 style={{ margin: 0 }}>Workspace</h1>
          <p className="muted" style={{ margin: '4px 0 0' }}>
            {me.user?.name} · {me.user?.email}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn premium" onClick={() => setPremium(true)}>
            ✦ Deep Analysis — coming soon
          </button>
          <button
            className="btn ghost"
            onClick={async () => {
              await logout()
              window.location.reload()
            }}
          >
            Sign out
          </button>
        </div>
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

      {tab === 'saved' && <SavedTenders />}
      {tab === 'notes' && <Notes />}
      {tab === 'alerts' && <Alerts />}
      {tab === 'pipeline' && <Pipeline />}
      {tab === 'chats' && <Chats />}
      {tab === 'widgets' && <Widgets />}
      {tab === 'profile' && <ProfileSection name={me.user?.name || ''} email={me.user?.email || ''} />}

      {premium && <PremiumModal onClose={() => setPremium(false)} />}
    </div>
  )
}

function SavedTenders() {
  const [items, setItems] = useState<SavedTenderItem[]>([])
  const [bidNumber, setBidNumber] = useState('')
  const [error, setError] = useState<string | null>(null)

  const load = () =>
    listSavedTenders()
      .then((r) => setItems(r.items))
      .catch((e: Error) => setError(e.message))

  useEffect(() => {
    load()
  }, [])

  const onSave = async () => {
    const bn = bidNumber.trim()
    if (!bn) return
    await saveTender(bn)
    setBidNumber('')
    load()
  }

  return (
    <div className="panel">
      <h3 style={{ marginTop: 0 }}>Saved tenders</h3>
      <div className="filter-actions">
        <input
          className="input mono"
          placeholder="Bid number, e.g. GEM/2026/B/…"
          value={bidNumber}
          onChange={(e) => setBidNumber(e.target.value)}
        />
        <button className="btn primary" onClick={onSave}>
          Save
        </button>
        <span className="muted" style={{ fontSize: 13 }}>
          or save from a tender's detail page.
        </span>
      </div>
      {error && <p style={{ color: 'var(--danger)' }}>{error}</p>}
      {items.length === 0 ? (
        <div className="empty">No saved tenders yet.</div>
      ) : (
        items.map((it) => (
          <div key={it.id} className="row">
            <Link className="mono" to={`/bid?bid_number=${encodeURIComponent(it.bid_number)}`}>
              {it.bid_number}
            </Link>
            <span className="muted">{it.note || ''}</span>
            <span style={{ flex: 1 }} />
            <button className="btn ghost" onClick={() => removeSavedTender(it.id).then(load)}>
              Remove
            </button>
          </div>
        ))
      )}
    </div>
  )
}

function Notes() {
  const [notes, setNotes] = useState<NoteItem[]>([])
  const [body, setBody] = useState('')
  const [tag, setTag] = useState('')
  const [error, setError] = useState<string | null>(null)

  const load = () => listNotes().then((r) => setNotes(r.items)).catch((e: Error) => setError(e.message))
  useEffect(() => {
    load()
  }, [])

  const onAdd = async () => {
    const b = body.trim()
    if (!b) return
    const tags = tag.trim() ? tag.split(',').map((t) => t.trim()).filter(Boolean) : undefined
    await createNote(b, { tags })
    setBody('')
    setTag('')
    load()
  }

  return (
    <div className="panel">
      <h3 style={{ marginTop: 0 }}>Notes</h3>
      <div className="filter-actions">
        <input
          className="input"
          placeholder="Note text…"
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
        <input
          className="input"
          placeholder="Tags (comma-separated)"
          value={tag}
          onChange={(e) => setTag(e.target.value)}
        />
        <button className="btn primary" onClick={onAdd}>
          Add note
        </button>
      </div>
      {error && <p style={{ color: 'var(--danger)' }}>{error}</p>}
      {notes.length === 0 ? (
        <div className="empty">No notes yet.</div>
      ) : (
        notes.map((n) => (
          <div key={n.id} className="row">
            <div style={{ flex: 1 }}>
              <div>{n.body}</div>
              {n.tags.length > 0 && (
                <div style={{ marginTop: 4 }}>
                  {n.tags.map((t) => (
                    <span key={t} className="chip" style={{ marginRight: 6 }}>
                      {t}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <button className="btn ghost" onClick={() => removeNote(n.id).then(load)}>
              Delete
            </button>
          </div>
        ))
      )}
    </div>
  )
}

function Alerts() {
  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)

  const load = () => listAlerts().then((r) => setAlerts(r.items)).catch((e: Error) => setError(e.message))
  useEffect(() => {
    load()
  }, [])

  const onAdd = async () => {
    const n = name.trim()
    if (!n) return
    await createAlert(n)
    setName('')
    load()
  }

  return (
    <div className="panel">
      <h3 style={{ marginTop: 0 }}>Alerts</h3>
      <div className="filter-actions">
        <input
          className="input"
          placeholder="Alert name…"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button className="btn primary" onClick={onAdd}>
          Add alert
        </button>
      </div>
      {error && <p style={{ color: 'var(--danger)' }}>{error}</p>}
      {alerts.length === 0 ? (
        <div className="empty">No alerts yet.</div>
      ) : (
        alerts.map((a) => (
          <div key={a.id} className="row">
            <span>{a.name}</span>
            <span className="muted">{a.frequency || ''}</span>
            <span style={{ flex: 1 }} />
            <button className="btn ghost" onClick={() => removeAlert(a.id).then(load)}>
              Delete
            </button>
          </div>
        ))
      )}
    </div>
  )
}

function Pipeline() {
  const [board, setBoard] = useState<PipelineBoard | null>(null)
  const [bidNumber, setBidNumber] = useState('')
  const [error, setError] = useState<string | null>(null)

  const load = () => listPipeline().then(setBoard).catch((e: Error) => setError(e.message))
  useEffect(() => {
    load()
  }, [])

  const onAdd = async () => {
    const bn = bidNumber.trim()
    if (!bn) return
    await addToPipeline(bn, 'new')
    setBidNumber('')
    load()
  }

  return (
    <div className="panel">
      <h3 style={{ marginTop: 0 }}>Pipeline</h3>
      <div className="filter-actions">
        <input
          className="input mono"
          placeholder="Bid number…"
          value={bidNumber}
          onChange={(e) => setBidNumber(e.target.value)}
        />
        <button className="btn primary" onClick={onAdd}>
          Add to pipeline
        </button>
      </div>
      {error && <p style={{ color: 'var(--danger)' }}>{error}</p>}
      {board && (
        <div className="pipeline-board">
          {board.stages.map((stage) => (
            <div key={stage} className="pipeline-col">
              <div className="pipeline-col-head">{stage}</div>
              {(board.board[stage] || []).map((item) => (
                <div key={item.id} className="pipeline-card">
                  <Link className="mono" to={`/bid?bid_number=${encodeURIComponent(item.bid_number)}`}>
                    {item.bid_number}
                  </Link>
                  <div className="pipeline-card-actions">
                    {board.stages.map((s) => (
                      <button key={s} className="btn ghost" disabled={s === stage} onClick={() => movePipeline(item.id, s).then(load)}>
                        →{s}
                      </button>
                    ))}
                    <button className="btn ghost" onClick={() => removePipeline(item.id).then(load)}>
                      ×
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ProfileSection({ name, email }: { name: string; email: string }) {
  const [tags, setTags] = useState<string[]>([])

  useEffect(() => {
    listTags().then((r) => setTags(r.items.map((t) => t.name)))
  }, [])

  return (
    <div className="panel">
      <h3 style={{ marginTop: 0 }}>Profile</h3>
      <p>
        <strong>{name}</strong> · <span className="muted">{email}</span>
      </p>
      <p>
        <strong>Tags:</strong> {tags.length ? tags.join(', ') : '—'}
      </p>
      <p className="muted">Preferences (timezone, default view) are coming soon.</p>
    </div>
  )
}

function Chats() {
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = () =>
    listChatSessions()
      .then((r) => setSessions(r.items))
      .catch((e: Error) => setError(e.message))
  useEffect(() => {
    load()
  }, [])

  return (
    <div className="panel">
      <h3 style={{ marginTop: 0 }}>Chat history</h3>
      {error && <p style={{ color: 'var(--danger)' }}>{error}</p>}
      {sessions.length === 0 ? (
        <div className="empty">No saved conversations yet. Ask a question to start one.</div>
      ) : (
        sessions.map((s) => (
          <div key={s.id} className="row">
            <Link className="mono" to={`/?session=${s.id}`}>
              {s.title || 'Untitled conversation'}
            </Link>
            <span className="muted">{s.updated_at ? s.updated_at.slice(0, 10) : ''}</span>
            <span style={{ flex: 1 }} />
            <button className="btn ghost" onClick={() => deleteChatSession(s.id).then(load)}>
              Delete
            </button>
          </div>
        ))
      )}
    </div>
  )
}

function Widgets() {
  const [items, setItems] = useState<SavedWidgetItem[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = () =>
    listSavedWidgets()
      .then((r) => setItems(r.items))
      .catch((e: Error) => setError(e.message))
  useEffect(() => {
    load()
  }, [])

  return (
    <div>
      {error && <p style={{ color: 'var(--danger)' }}>{error}</p>}
      {items.length === 0 ? (
        <div className="empty">No saved widgets yet. Save an insight from Ask.</div>
      ) : (
        items.map((it) => {
          const w = {
            id: `saved-${it.id}`,
            kind: it.kind as WidgetKind,
            title: it.title || '',
            data: (it.data as Record<string, unknown>) || {},
          }
          return (
            <div key={it.id} className={isWide(w.kind) ? 'widget-cell wide' : 'widget-cell'}>
              {renderWidget(w)}
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 6 }}>
                <button className="btn ghost" onClick={() => removeSavedWidget(it.id).then(load)}>
                  Remove
                </button>
              </div>
            </div>
          )
        })
      )}
    </div>
  )
}

function PremiumModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2 style={{ marginTop: 0 }}>✦ Deep Analysis</h2>
        <p>
          Deep Analysis will provide bid/no-bid assessment, compliance analysis, BOQ intelligence, and
          detailed strategic recommendations.
        </p>
        <p className="muted">Coming soon.</p>
        <button className="btn primary" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  )
}
