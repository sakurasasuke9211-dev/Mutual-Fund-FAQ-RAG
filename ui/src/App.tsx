import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertTriangle, ArrowRight, BookOpenText, Check, Copy, ExternalLink,
  Menu, MessageSquareText, Plus, RefreshCw, Send, ShieldCheck, X,
} from 'lucide-react'
import { ApiError, api } from './api'
import type { ChatResponse, ConnectionStatus, MessageRecord, ThreadSummary } from './types'
import './App.css'

const ACTIVE_THREAD_KEY = 'fundfacts.activeThread'
const EXAMPLES = [
  'What is the expense ratio of HDFC ELSS Tax Saver Fund?',
  'What is the lock-in period for HDFC ELSS Tax Saver Fund?',
  'What is the exit load for HDFC Large Cap Fund?',
]

function shortThreadName(threadId: string) {
  return `Conversation ${threadId.slice(0, 8)}`
}

/** Prefer first-question titles from the API; otherwise Conversation 1, 2, … by age. */
function conversationLabels(threads: ThreadSummary[]): Map<string, string> {
  const byCreated = [...threads].sort(
    (left, right) => new Date(left.created_at).getTime() - new Date(right.created_at).getTime(),
  )
  const labels = new Map<string, string>()
  byCreated.forEach((thread, index) => {
    const title = thread.title?.trim()
    if (title && title !== 'New conversation') {
      labels.set(thread.thread_id, title)
    } else {
      labels.set(thread.thread_id, `Conversation ${index + 1}`)
    }
  })
  return labels
}

function relativeTime(value: string) {
  const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000)
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  if (Math.abs(seconds) < 60) return formatter.format(seconds, 'second')
  const minutes = Math.round(seconds / 60)
  if (Math.abs(minutes) < 60) return formatter.format(minutes, 'minute')
  const hours = Math.round(minutes / 60)
  if (Math.abs(hours) < 24) return formatter.format(hours, 'hour')
  return formatter.format(Math.round(hours / 24), 'day')
}

function toAssistantMessage(response: ChatResponse): MessageRecord {
  return {
    message_id: crypto.randomUUID(),
    thread_id: response.thread_id,
    role: 'assistant',
    content: response.answer,
    metadata: {
      response_type: response.response_type,
      source_url: response.source_url,
      source_title: response.source_title,
      last_updated: response.last_updated,
      educational_link: response.educational_link,
    },
    created_at: new Date().toISOString(),
  }
}

function App() {
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [activeThreadId, setActiveThreadId] = useState<string | null>(
    () => localStorage.getItem(ACTIVE_THREAD_KEY),
  )
  const [messages, setMessages] = useState<MessageRecord[]>([])
  const [draft, setDraft] = useState('')
  const [connection, setConnection] = useState<ConnectionStatus>('checking')
  const [serviceError, setServiceError] = useState<string | null>(null)
  const [chatError, setChatError] = useState<string | null>(null)
  const [isLoadingThreads, setIsLoadingThreads] = useState(true)
  const [isLoadingMessages, setIsLoadingMessages] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const scrollAnchor = useRef<HTMLDivElement>(null)

  const checkHealth = useCallback(async () => {
    setConnection('checking')
    try {
      await api.health()
      setConnection('connected')
      setServiceError(null)
    } catch (error) {
      setConnection('disconnected')
      setServiceError(error instanceof Error ? error.message : 'Service unavailable.')
    }
  }, [])

  const loadThreads = useCallback(async () => {
    setIsLoadingThreads(true)
    try {
      const result = await api.listThreads()
      setThreads(result)
      const stored = localStorage.getItem(ACTIVE_THREAD_KEY)
      if (stored && result.some((thread) => thread.thread_id === stored)) {
        setActiveThreadId(stored)
      } else if (stored) {
        localStorage.removeItem(ACTIVE_THREAD_KEY)
        setActiveThreadId(null)
      }
    } catch (error) {
      setServiceError(error instanceof Error ? error.message : 'Could not load conversations.')
    } finally {
      setIsLoadingThreads(false)
    }
  }, [])

  useEffect(() => {
    void checkHealth()
    void loadThreads()
  }, [checkHealth, loadThreads])

  useEffect(() => {
    if (!activeThreadId) {
      setMessages([])
      return
    }
    let cancelled = false
    setIsLoadingMessages(true)
    setChatError(null)
    localStorage.setItem(ACTIVE_THREAD_KEY, activeThreadId)
    api.getMessages(activeThreadId)
      .then((result) => { if (!cancelled) setMessages(result) })
      .catch(async (error) => {
        if (cancelled) return
        if (error instanceof ApiError && error.status === 404) {
          localStorage.removeItem(ACTIVE_THREAD_KEY)
          setActiveThreadId(null)
          await loadThreads()
          return
        }
        setChatError(error instanceof Error ? error.message : 'Could not load this conversation.')
      })
      .finally(() => { if (!cancelled) setIsLoadingMessages(false) })
    return () => { cancelled = true }
  }, [activeThreadId, loadThreads])

  useEffect(() => {
    scrollAnchor.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isSending])

  async function createThread() {
    setChatError(null)
    try {
      const created = await api.createThread()
      const thread: ThreadSummary = {
        thread_id: created.thread_id,
        created_at: created.created_at,
        updated_at: created.created_at,
        message_count: 0,
        title: 'New conversation',
      }
      setThreads((current) => [thread, ...current])
      setActiveThreadId(created.thread_id)
      setMessages([])
      localStorage.setItem(ACTIVE_THREAD_KEY, created.thread_id)
      setSidebarOpen(false)
      return created.thread_id
    } catch (error) {
      setChatError(error instanceof Error ? error.message : 'Could not create a conversation.')
      return null
    }
  }

  async function sendQuestion(question = draft) {
    const query = question.trim()
    if (!query || isSending || isLoadingThreads || query.length > 500) return
    setIsSending(true)
    setChatError(null)
    setDraft('')

    let threadId = activeThreadId
    // Railway memory/ephemeral store drops threads on redeploy; localStorage can go stale.
    if (threadId && !threads.some((thread) => thread.thread_id === threadId)) {
      localStorage.removeItem(ACTIVE_THREAD_KEY)
      setActiveThreadId(null)
      threadId = null
    }
    if (!threadId) threadId = await createThread()
    if (!threadId) {
      setDraft(query)
      setIsSending(false)
      return
    }

    const optimistic: MessageRecord = {
      message_id: crypto.randomUUID(),
      thread_id: threadId,
      role: 'user',
      content: query,
      metadata: {},
      created_at: new Date().toISOString(),
    }
    setMessages((current) => [...current, optimistic])

    try {
      let response: ChatResponse
      try {
        response = await api.chat(threadId, query)
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 404) throw error
        localStorage.removeItem(ACTIVE_THREAD_KEY)
        setActiveThreadId(null)
        const freshThreadId = await createThread()
        if (!freshThreadId) throw error
        threadId = freshThreadId
        setMessages((current) =>
          current.map((message) =>
            message.message_id === optimistic.message_id
              ? { ...message, thread_id: freshThreadId }
              : message,
          ),
        )
        response = await api.chat(freshThreadId, query)
      }
      setMessages((current) => [...current, toAssistantMessage(response)])
      await loadThreads()
    } catch (error) {
      setChatError(error instanceof Error ? error.message : 'The question could not be sent.')
      setDraft(query)
      setMessages((current) => current.filter((message) => message.message_id !== optimistic.message_id))
    } finally {
      setIsSending(false)
    }
  }

  const threadLabels = conversationLabels(threads)
  const activeLabel = activeThreadId
    ? threadLabels.get(activeThreadId) || shortThreadName(activeThreadId)
    : null

  return (
    <div className="app-shell">
      {sidebarOpen && <button className="sidebar-backdrop" aria-label="Close conversations" onClick={() => setSidebarOpen(false)} />}
      <aside className={`sidebar ${sidebarOpen ? 'sidebar--open' : ''}`}>
        <div className="brand">
          <span className="brand__mark"><ShieldCheck size={20} strokeWidth={2.2} /></span>
          <span><strong>FundFacts</strong><small>Assistant</small></span>
          <button className="icon-button sidebar__close" onClick={() => setSidebarOpen(false)} aria-label="Close sidebar"><X size={19} /></button>
        </div>
        <div className="sidebar__body">
          <button className="new-thread" onClick={() => void createThread()}><Plus size={17} /> New conversation</button>
          <div className="thread-list" aria-label="Conversations">
            {isLoadingThreads ? (
              <><div className="thread-skeleton" /><div className="thread-skeleton" /></>
            ) : threads.length === 0 ? (
              <p className="empty-threads">No conversations yet.</p>
            ) : threads.map((thread) => (
              <button
                key={thread.thread_id}
                className={`thread-item ${thread.thread_id === activeThreadId ? 'thread-item--active' : ''}`}
                onClick={() => { setActiveThreadId(thread.thread_id); setSidebarOpen(false) }}
              >
                <MessageSquareText size={16} />
                <span>
                  <strong>{threadLabels.get(thread.thread_id) || shortThreadName(thread.thread_id)}</strong>
                  <small>{thread.message_count} messages · {relativeTime(thread.updated_at)}</small>
                </span>
              </button>
            ))}
          </div>
        </div>
        <div className="scope">
          <span>SCOPE</span>
          <p>Answers cover five indexed HDFC mutual fund schemes, sourced from public Groww scheme pages. Facts only — no investment advice.</p>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <button className="icon-button mobile-menu" onClick={() => setSidebarOpen(true)} aria-label="Open conversations"><Menu size={21} /></button>
          <div><strong>{activeLabel || 'FundFacts Assistant'}</strong><small>Source-backed mutual fund information</small></div>
          <div className={`connection connection--${connection}`}>
            <span />{connection === 'connected' ? 'Connected' : connection === 'checking' ? 'Checking' : 'Disconnected'}
          </div>
        </header>

        <section className="disclaimer">
          <div><ShieldCheck size={15} /> <strong>Facts-only. No investment advice.</strong> Answers are limited to indexed public scheme information.</div>
          <small>Do not enter PAN, Aadhaar, account numbers, OTPs, phone numbers, or email addresses.</small>
        </section>

        {serviceError && (
          <section className="service-alert" role="alert">
            <div><AlertTriangle size={17} /><span>The information service is currently unreachable. New questions can’t be sent until it’s back.</span></div>
            <button onClick={() => { void checkHealth(); void loadThreads() }}><RefreshCw size={15} /> Retry</button>
          </section>
        )}

        <section className="conversation">
          <div className="conversation__inner">
            {isLoadingMessages ? (
              <div className="message-loading" aria-label="Loading conversation"><div /><div /><div /></div>
            ) : messages.length === 0 ? (
              <WelcomeState onQuestion={(question) => void sendQuestion(question)} />
            ) : (
              <div className="messages" aria-live="polite">
                {messages.map((message) => <ChatMessage key={message.message_id} message={message} />)}
                {isSending && <TypingIndicator />}
                <div ref={scrollAnchor} />
              </div>
            )}
          </div>
        </section>

        <footer className="composer-wrap">
          {chatError && (
            <div className="chat-error" role="alert">
              <AlertTriangle size={15} /><span>{chatError}</span>
              <button onClick={() => void sendQuestion()}>Retry</button>
            </div>
          )}
          <div className="composer">
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value.slice(0, 500))}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  void sendQuestion()
                }
              }}
              rows={1}
              maxLength={500}
              placeholder="Ask about expense ratio, exit load, SIP minimum, lock-in…"
              aria-label="Ask a factual mutual fund question"
              disabled={isSending || isLoadingThreads || connection === 'disconnected'}
            />
            <button
              className="send-button"
              onClick={() => void sendQuestion()}
              disabled={!draft.trim() || isSending || isLoadingThreads || connection === 'disconnected'}
              aria-label="Send question"
            ><Send size={18} /></button>
          </div>
          <div className="composer-meta">
            <span>Enter to send · Shift + Enter for a new line</span>
            <span className={draft.length > 450 ? 'character-count character-count--near' : 'character-count'}>{draft.length}/500</span>
          </div>
        </footer>
      </main>
    </div>
  )
}

function WelcomeState({ onQuestion }: { onQuestion: (question: string) => void }) {
  return (
    <div className="welcome">
      <span className="welcome__icon"><BookOpenText size={25} /></span>
      <h1>Ask factual questions about Mutual Funds</h1>
      <p>Get concise answers grounded in indexed Groww scheme pages, with a source and last-updated date.</p>
      <div className="examples">
        {EXAMPLES.map((question) => (
          <button key={question} onClick={() => onQuestion(question)}><span>{question}</span><ArrowRight size={16} /></button>
        ))}
      </div>
    </div>
  )
}

function ChatMessage({ message }: { message: MessageRecord }) {
  const [copied, setCopied] = useState(false)
  const isRefusal = message.metadata.response_type === 'refusal'

  async function copyMessage() {
    await navigator.clipboard.writeText(message.content)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }

  if (message.role === 'user') {
    return <div className="message-row message-row--user"><div className="user-message">{message.content}</div></div>
  }

  return (
    <div className={`assistant-message ${isRefusal ? 'assistant-message--refusal' : ''}`}>
      <div className="assistant-message__icon">{isRefusal ? <AlertTriangle size={17} /> : <ShieldCheck size={17} />}</div>
      <div className="assistant-message__body">
        <div className="assistant-message__heading">
          <strong>{isRefusal ? 'Facts-only guidance' : 'FundFacts'}</strong>
          <button className="copy-button" onClick={() => void copyMessage()} aria-label="Copy answer">
            {copied ? <Check size={15} /> : <Copy size={15} />} {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
        <p>{message.content}</p>
        {!isRefusal && message.metadata.source_url && (
          <a className="source-card" href={message.metadata.source_url} target="_blank" rel="noreferrer">
            <span className="source-card__icon"><BookOpenText size={17} /></span>
            <span>
              <small>SOURCE</small>
              <strong>{message.metadata.source_title || 'View indexed Groww scheme page'}</strong>
              {message.metadata.last_updated && <em>Source last updated: {message.metadata.last_updated}</em>}
            </span>
            <ExternalLink size={17} />
          </a>
        )}
        {isRefusal && message.metadata.educational_link && (
          <a className="education-link" href={message.metadata.educational_link.url} target="_blank" rel="noreferrer">
            {message.metadata.educational_link.label} <ExternalLink size={15} />
          </a>
        )}
      </div>
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="assistant-message">
      <div className="assistant-message__icon"><ShieldCheck size={17} /></div>
      <div className="typing" aria-label="FundFacts is preparing an answer"><span /><span /><span /></div>
    </div>
  )
}

export default App
