import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  appendChatMessage,
  askStream,
  askHints,
  createChatSession,
  getChatSession,
  putChatWidgets,
  saveWidget,
} from '../api/client'
import { renderMarkdown } from '../lib/markdown'
import { getDiscoveryContext, setDiscoveryContext } from '../state/context'
import { isWide, removeWidget, upsertWidget } from '../state/collage'
import { useAuth } from '../state/auth'
import { renderWidget } from '../components/collage/renderWidget'
import type { DiscoveryContext, Widget } from '../lib/types'

interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  thinking?: string
}

interface Interpretation {
  summary: string
  chips: { label: string; prompt: string }[]
}

// Eight starting examples spanning the three journeys (sellers, OEMs, buyers).
const SUGGESTED = [
  'Find live solar EPC tenders in Gujarat',
  'Which high-value tenders need OEM authorisation?',
  'Show active tenders from Indian Railways closing this month',
  'Compare BOQ line items across these bids',
  'Find tenders where I can bid as an OEM in solar',
  'What are the largest live healthcare tenders?',
  'Show tenders with detailed BOQs',
  'Which ministries are buying IT hardware right now?',
]

const STORE_KEY = 'tenderising.chat'

interface Stored {
  sessionId: string | null
  messages: Message[]
  widgets: Widget[]
  conclusion: string | null
}

function loadStored(): Stored {
  try {
    const raw = sessionStorage.getItem(STORE_KEY)
    if (raw) {
      const s = JSON.parse(raw) as Partial<Stored>
      return {
        sessionId: s.sessionId ?? null,
        messages: Array.isArray(s.messages) ? (s.messages as Message[]) : [],
        widgets: Array.isArray(s.widgets) ? (s.widgets as Widget[]) : [],
        conclusion: s.conclusion ?? null,
      }
    }
  } catch {
    // ignore malformed storage
  }
  return { sessionId: null, messages: [], widgets: [], conclusion: null }
}

function dim(index: number, length: number): number {
  const fromEnd = length - 1 - index
  return Math.max(0.4, 1 - fromEnd * 0.14)
}

function contextualHints(messages: Message[]): { label: string; prompt: string }[] {
  const last = [...messages].reverse().find((m) => m.role === 'user')
  const base = last?.content?.trim() || 'these tenders'
  return [
    { label: 'High value only', prompt: `${base}, high value only` },
    { label: 'Closing soon', prompt: `${base}, closing soon` },
    { label: 'Compare top matches', prompt: `compare the top matches for ${base}` },
  ]
}

export default function Ask() {
  const { authenticated } = useAuth()
  const [params] = useSearchParams()
  const sessionParam = params.get('session')

  const initial = useMemo(loadStored, [])
  const counter = useRef(Math.max(1, ...initial.messages.map((m) => m.id)) + 1)
  const makeId = useCallback(() => counter.current++, [])

  const [context, setContext] = useState<DiscoveryContext | null>(null)
  const [messages, setMessages] = useState<Message[]>(initial.messages)
  const [widgets, setWidgets] = useState<Widget[]>(initial.widgets)
  const [sessionId, setSessionId] = useState<string | null>(initial.sessionId)
  const [conclusion, setConclusion] = useState<string | null>(initial.conclusion)
  const [widgetsCollapsed, setWidgetsCollapsed] = useState(initial.widgets.length > 0)
  const [interpreted, setInterpreted] = useState<Interpretation | null>(null)
  const [followups, setFollowups] = useState<string[]>([])
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set())
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [ack, setAck] = useState<string | null>(null)
  const threadRef = useRef<HTMLDivElement>(null)

  // Restore Discovery context (set from the Discovery page before navigating here).
  useEffect(() => {
    const ctx = getDiscoveryContext()
    if (ctx && ctx.bids.length) setContext(ctx)
  }, [])

  // Load a specific historic session when navigated to with ?session=<id>.
  useEffect(() => {
    if (!authenticated || !sessionParam) return
    getChatSession(sessionParam)
      .then((s) => {
        setSessionId(s.id)
        setMessages(s.messages.map((m) => ({ id: makeId(), role: m.role as 'user' | 'assistant', content: m.content })))
        setWidgets(s.widgets || [])
        setWidgetsCollapsed(true)
        setConclusion(null)
        setInterpreted(null)
      })
      .catch(() => {})
  }, [authenticated, sessionParam, makeId])

  // Persist the thread so it survives refresh and route changes.
  useEffect(() => {
    sessionStorage.setItem(
      STORE_KEY,
      JSON.stringify({ sessionId, messages, widgets, conclusion }),
    )
  }, [sessionId, messages, widgets, conclusion])

  useEffect(() => {
    const el = threadRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, ack])

  const update = (id: number, fn: (c: string) => string) =>
    setMessages((m) => m.map((x) => (x.id === id ? { ...x, content: fn(x.content) } : x)))

  const updateThinking = (id: number, fn: (t: string) => string) =>
    setMessages((m) => m.map((x) => (x.id === id ? { ...x, thinking: fn(x.thinking || '') } : x)))

  const newChat = () => {
    setMessages([])
    setWidgets([])
    setConclusion(null)
    setInterpreted(null)
    setFollowups([])
    setAck(null)
    setContext(null)
    setSessionId(null)
    setSavedIds(new Set())
    setDiscoveryContext(null)
  }

  const send = async (text?: string) => {
    const msg = (text ?? input).trim()
    if (!msg || streaming) return
    const history = messages.map((m) => ({ role: m.role, content: m.content }))
    setInput('')
    setWidgets([])
    setAck(null)
    setConclusion(null)
    setInterpreted(null)
    setFollowups([])
    setWidgetsCollapsed(false)

    // Ensure a server session and persist the user turn (Google users only).
    let sid = sessionId
    if (authenticated) {
      if (!sid) {
        try {
          sid = (await createChatSession()).id
          setSessionId(sid)
        } catch {
          sid = null
        }
      }
      if (sid) appendChatMessage(sid, 'user', msg).catch(() => {})
    }

    const userMsg: Message = { id: makeId(), role: 'user', content: msg }
    const asstId = makeId()
    setMessages((m) => [...m, userMsg, { id: asstId, role: 'assistant', content: '' }])
    setStreaming(true)

    let collectedWidgets: Widget[] = []
    let finalAnswer = ''

    try {
      await askStream(msg, context, history, (ev) => {
        if (ev.type === 'thinking') updateThinking(asstId, (t) => t + (ev.delta || ''))
        else if (ev.type === 'answer') update(asstId, (c) => c + (ev.delta || ''))
        else if (ev.type === 'tool') update(asstId, () => '')
        else if (ev.type === 'widget' && ev.widget) {
          collectedWidgets = upsertWidget(collectedWidgets, ev.widget!)
          setWidgets((w) => upsertWidget(w, ev.widget!))
        } else if (ev.type === 'interpreted') {
          setInterpreted({ summary: ev.summary || '', chips: ev.chips || [] })
        } else if (ev.type === 'ack') setAck(ev.message || null)
        else if (ev.type === 'done') {
          finalAnswer = ev.answer || ''
          if (!finalAnswer && collectedWidgets.length > 0) {
            finalAnswer = `Here's what I found across ${collectedWidgets.length} insights.`
          }
          update(asstId, () => finalAnswer)
          setConclusion(finalAnswer)
        } else if (ev.type === 'error') update(asstId, (c) => c + `\n[error: ${ev.message}]`)
      })
    } catch (e) {
      update(asstId, (c) => c + `\n[error: ${String(e)}]`)
    } finally {
      setStreaming(false)
      if (authenticated && sid) {
        if (finalAnswer) appendChatMessage(sid, 'assistant', finalAnswer).catch(() => {})
        putChatWidgets(sid, collectedWidgets).catch(() => {})
      }
      // Fetch context-relevant follow-ups once the turn is done (non-blocking).
      if (finalAnswer) {
        askHints(msg, history, finalAnswer)
          .then(setFollowups)
          .catch(() => {})
      }
    }
  }

  const dismissContext = () => {
    setContext(null)
    setDiscoveryContext(null)
  }

  const handleSave = (w: Widget) => async () => {
    if (!authenticated) {
      window.location.href = '/api/auth/login'
      return
    }
    try {
      await saveWidget(w.kind, w.data, w.title, sessionId ?? undefined)
      setSavedIds((s) => new Set(s).add(w.id))
    } catch {
      // ignore — button remains available to retry
    }
  }

  const followupItems = followups.map((f) => ({ label: f, prompt: f }))
  const hint =
    messages.length === 0
      ? SUGGESTED.map((p) => ({ label: p, prompt: p }))
      : followupItems.length > 0
        ? followupItems
        : contextualHints(messages)

  return (
    <div className="ask-shell">
      <div className="collage">
        {interpreted && (
          <div className="interpreted-bar" style={{ gridColumn: '1 / -1' }}>
            <div className="interpreted-summary">{interpreted.summary}</div>
            {interpreted.chips.length > 0 && (
              <div className="interpreted-chips">
                {interpreted.chips.map((c) => (
                  <button key={c.label} className="prompt-chip" onClick={() => send(c.prompt)}>
                    {c.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {widgets.length === 0 ? (
          <div className="collage-empty" style={{ gridColumn: '1 / -1' }}>
            <p>
              Ask a question and the intelligence canvas will appear here — result tables, summaries,
              deadline charts, and buyer insights.
            </p>
          </div>
        ) : widgetsCollapsed ? (
          <button className="collage-collapsed" style={{ gridColumn: '1 / -1' }} onClick={() => setWidgetsCollapsed(false)}>
            {widgets.length} saved insights — tap to show
          </button>
        ) : (
          widgets.map((w) => (
            <div key={w.id} className={isWide(w.kind) ? 'widget-cell wide' : 'widget-cell'}>
              {renderWidget(
                w,
                () => setWidgets((list) => removeWidget(list, w.id)),
                savedIds.has(w.id) ? undefined : handleSave(w),
              )}
            </div>
          ))
        )}
      </div>

      <div className="chat">
        <div className="chat-toolbar">
          <span className="chat-toolbar-title">Conversation</span>
          <button className="btn ghost" onClick={newChat} disabled={streaming}>
            + New chat
          </button>
        </div>

        <div className="chat-thread" ref={threadRef}>
          {ack && <div className="ack-note">{ack}</div>}
          {messages.map((m, i) => (
            <div key={m.id} className={`msg ${m.role}`} style={{ opacity: dim(i, messages.length) }}>
              <div className="bubble">
                {m.thinking ? <div className="think-text">{m.thinking}</div> : null}
                {m.content ? (
                  m.role === 'assistant' ? (
                    <div className="md" dangerouslySetInnerHTML={{ __html: renderMarkdown(m.content) }} />
                  ) : (
                    <div>{m.content}</div>
                  )
                ) : (
                  m.role === 'assistant' && streaming && !m.thinking ? 'Thinking…' : ''
                )}
              </div>
            </div>
          ))}
        </div>

        {context && (
          <div className="context-chip">
            Using {(context.total ?? context.bids.length).toLocaleString()} bids from Discovery
            <button onClick={dismissContext} aria-label="Remove context">
              ×
            </button>
          </div>
        )}

        <div className="prompt-chips">
          {hint.map((h) => (
            <button key={h.label} className="prompt-chip" onClick={() => send(h.prompt)}>
              {h.label}
            </button>
          ))}
        </div>

        {conclusion && <div className="conclusion">{conclusion}</div>}

        <div className="composer">
          <textarea
            value={input}
            placeholder="Ask about bids, buyers, awards, documents…"
            rows={2}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                send()
              }
            }}
          />
          <button className="btn primary" disabled={streaming} onClick={() => send()}>
            Ask
          </button>
        </div>
      </div>
    </div>
  )
}
