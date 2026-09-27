import { useEffect, useRef, useState } from 'react'
import type { SyntheticEvent } from 'react'
import { Link, matchPath, useLocation, useNavigate } from 'react-router-dom'
import { ApiError, clearChatHistory, fetchChatHistory, fetchProduct, sendChatMessage } from '../api/client'
import { useAuth } from '../lib/auth'
import { CHAT_RESULTS_PATH, useChatSearch } from '../lib/chatSearch'
import { formatPrice } from '../lib/format'
import ProductImage from './ProductImage'
import type { ChatTurn, PageContext, ProductCard, PublicUser } from '../types'

interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  products?: ProductCard[]
  /** Set when this reply's catalogue search was sent to the Products page. */
  searchTotal?: number
  error?: boolean
  /** For failed sends: the shopper's text, so "Try again" can resend it. */
  retryText?: string
}

// Status shown while the assistant works, so a slow answer never looks like a frozen chat.
const PENDING_STAGES = [
  { after: 0, text: 'Thinking…' },
  { after: 5000, text: 'Checking the catalogue and stock…' },
  { after: 15000, text: 'Still working on it. Thanks for your patience…' },
]

const MAX_MESSAGE_CHARS = 2000 // matches MAX_CHAT_MESSAGE_CHARS in backend/models.py
const MAX_HISTORY_TURNS = 12 // matches MAX_HISTORY_TURNS in backend/models.py

const SUGGESTIONS = ['What hoodies do you have?', 'Show me t-shirts', 'Do you have a Morse shirt in medium?']
const PRODUCT_PAGE_SUGGESTIONS = ['Do you have this in pink?', 'Is this in stock in medium?', 'How much is this?']

// Older saved replies used Markdown bold; the widget shows plain text.
const plain = (text: string) => text.replace(/\*\*(.+?)\*\*/g, '$1')

export default function ChatWidget() {
  const { user, token, restoring } = useAuth()
  const [open, setOpen] = useState(false)

  return (
    <div className="chat">
      {open && !restoring && (
        // Keyed on the account: logging in/out swaps to that shopper's conversation with no leftovers.
        <ChatPanel key={user?.id ?? 'guest'} user={user} token={token} onClose={() => setOpen(false)} />
      )}
      <button
        type="button"
        className="chat__launcher"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label={open ? 'Close chat' : 'Open chat'}
      >
        {open ? '✕' : (
          <svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true">
            <path
              fill="currentColor"
              d="M4 4h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H8l-4 4V6a2 2 0 0 1 2-2Zm3 6v2h2v-2H7Zm4 0v2h2v-2h-2Zm4 0v2h2v-2h-2Z"
            />
          </svg>
        )}
      </button>
    </div>
  )
}

interface PanelProps {
  user: PublicUser | null
  token: string | null
  onClose: () => void
}

function ChatPanel({ user, token, onClose }: PanelProps) {
  const { setResults } = useChatSearch()
  const navigate = useNavigate()
  const location = useLocation()
  const loggedIn = Boolean(user && token)

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [historyState, setHistoryState] = useState<'loading' | 'ready' | 'error'>(loggedIn ? 'loading' : 'ready')
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [viewedProduct, setViewedProduct] = useState<{ id: string; name: string } | null>(null)
  const [pendingStage, setPendingStage] = useState(0)
  const [historyAttempt, setHistoryAttempt] = useState(0)
  const nextId = useRef(1)
  const listRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Page context: which product (if any) the shopper is looking at right now.
  const productId = matchPath('/products/:productId', location.pathname)?.params.productId ?? null
  const pageContext: PageContext = { path: location.pathname + location.search, product_id: productId }
  const productName = viewedProduct && viewedProduct.id === productId ? viewedProduct.name : null

  // Logged-in shoppers: reload their saved conversation from the database.
  useEffect(() => {
    if (!loggedIn || !token) return
    fetchChatHistory(token)
      .then((res) => {
        setMessages(
          res.messages.map((m) => ({ id: nextId.current++, role: m.role, content: plain(m.content), products: m.products })),
        )
        setHistoryState('ready')
      })
      .catch(() => setHistoryState('error'))
  }, [loggedIn, token, historyAttempt])

  // Advance the "Thinking…" status while a reply is pending.
  useEffect(() => {
    if (!sending) return
    const timers = PENDING_STAGES.slice(1).map((stage, i) => setTimeout(() => setPendingStage(i + 1), stage.after))
    return () => timers.forEach(clearTimeout)
  }, [sending])

  // Show the product name in the "viewing" chip (display only; the backend resolves the product itself).
  useEffect(() => {
    if (!productId) return
    const controller = new AbortController()
    fetchProduct(productId, controller.signal)
      .then((p) => setViewedProduct({ id: p.product_id, name: p.name }))
      .catch(() => undefined)
    return () => controller.abort()
  }, [productId])

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, sending])

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const returning = loggedIn && messages.length > 0
  const firstName = user?.first_name ?? user?.name
  const greeting = returning
    ? `Welcome back, ${firstName}! Your earlier conversation is below. Pick up right where you left off.`
    : firstName
      ? `Hi ${firstName}! I’m the Campus Customs assistant. Ask me about sizes, colors, stock, or finding the right Yale gear.`
      : 'Hi! I’m the Campus Customs assistant. Ask me about sizes, colors, stock, or finding the right Yale gear.'

  async function send(text: string) {
    const message = text.trim()
    if (!message || sending || historyState === 'loading') return

    // Guests send this tab's turns as history; for logged-in shoppers the server uses saved history.
    const history: ChatTurn[] = loggedIn
      ? []
      : messages
          .filter((m, i, all) => !m.error && !all[i + 1]?.error) // skip failed exchanges
          .slice(-MAX_HISTORY_TURNS)
          .map((m) => ({ role: m.role, content: m.content }))

    setMessages((m) => [...m, { id: nextId.current++, role: 'user', content: message }])
    setDraft('')
    setPendingStage(0)
    setSending(true)
    try {
      const res = await sendChatMessage(message, history, token, pageContext)
      const search = res.search_results
      setMessages((m) => [
        ...m,
        {
          id: nextId.current++,
          role: 'assistant',
          content: res.reply,
          // A search's results appear on the Products page, so skip duplicate mini-cards in the bubble.
          products: search ? [] : res.products,
          searchTotal: search?.total_matches,
        },
      ])
      if (search) {
        setResults(search)
        navigate(CHAT_RESULTS_PATH)
      }
    } catch (err) {
      const api = err instanceof ApiError ? err : null
      setMessages((m) => [
        ...m,
        {
          id: nextId.current++,
          role: 'assistant',
          content: api?.message ?? 'Sorry, something went wrong. Please try again.',
          error: true,
          // Offer a resend for temporary problems (offline, timeout, busy, server); not for invalid input.
          retryText: !api || api.retryable ? message : undefined,
        },
      ])
    } finally {
      setSending(false)
    }
  }

  async function handleClear() {
    if (loggedIn && token) {
      if (!window.confirm('Delete your saved chat history with the Campus Customs assistant?')) return
      try {
        await clearChatHistory(token)
      } catch {
        return
      }
    }
    setMessages([])
  }

  /** Remove the failed exchange and send the same text again. */
  function retry(failed: ChatMessage) {
    if (!failed.retryText || sending) return
    setMessages((m) => {
      const i = m.findIndex((x) => x.id === failed.id)
      // Drop the error bubble and the user message right before it (send() re-adds it).
      return i > 0 && m[i - 1].role === 'user' ? [...m.slice(0, i - 1), ...m.slice(i + 1)] : m.filter((x) => x.id !== failed.id)
    })
    void send(failed.retryText)
  }

  function handleSubmit(e?: SyntheticEvent) {
    e?.preventDefault()
    void send(draft)
  }

  const suggestions = productId ? PRODUCT_PAGE_SUGGESTIONS : SUGGESTIONS

  return (
    <section className="chat__panel" aria-label="Campus Customs chat">
      <header className="chat__header">
        <span className="chat__avatar" aria-hidden="true">
          CC
          <span className="chat__status-dot" />
        </span>
        <div className="chat__heading">
          <p className="chat__title">Campus Customs Assistant</p>
          <p className="chat__subtitle">
            {loggedIn ? 'Saved to your account' : 'Guest chat, not saved after you leave'}
          </p>
        </div>
        <div className="chat__header-actions">
          {messages.length > 0 && (
            <button
              type="button"
              className="chat__clear"
              onClick={() => void handleClear()}
              disabled={sending}
              title={loggedIn ? 'Delete your saved chat history' : 'Start a new conversation'}
            >
              {loggedIn ? 'Clear history' : 'New chat'}
            </button>
          )}
          <button type="button" className="chat__close" onClick={onClose} aria-label="Close chat">
            ✕
          </button>
        </div>
      </header>

      <div className="chat__messages" ref={listRef} aria-live="polite">
        {historyState === 'loading' ? (
          <div className="chat__msg chat__msg--assistant chat__typing" aria-label="Loading your saved chat">
            <span />
            <span />
            <span />
          </div>
        ) : (
          <div className="chat__msg chat__msg--assistant">
            <p>{greeting}</p>
          </div>
        )}
        {historyState === 'error' && (
          <div className="chat__msg chat__msg--assistant chat__msg--error">
            <p>We couldn’t load your saved conversation. New messages will still be saved.</p>
            <button
              type="button"
              className="chat__retry"
              onClick={() => {
                setHistoryState('loading')
                setHistoryAttempt((a) => a + 1)
              }}
            >
              Try again
            </button>
          </div>
        )}
        {historyState !== 'loading' && messages.length === 0 && (
          <div className="chat__suggestions">
            {suggestions.map((s) => (
              <button key={s} type="button" className="chat__suggestion" onClick={() => void send(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`chat__msg chat__msg--${m.role} ${m.error ? 'chat__msg--error' : ''}`}>
            <p>{m.content}</p>
            {m.error && m.retryText && (
              <button type="button" className="chat__retry" onClick={() => retry(m)} disabled={sending}>
                Try again
              </button>
            )}
            {m.searchTotal !== undefined && (
              <Link to={CHAT_RESULTS_PATH} className="chat__results-link">
                {m.searchTotal > 0
                  ? `View ${m.searchTotal} result${m.searchTotal === 1 ? '' : 's'} on the Products page →`
                  : 'No matches, see the Products page →'}
              </Link>
            )}
            {m.products && m.products.length > 0 && (
              <div className="chat__products">
                {m.products.map((p) => (
                  <Link key={p.product_id} to={`/products/${p.product_id}`} className="chat__product">
                    <ProductImage src={p.image_url} alt="" />
                    <span className="chat__product-info">
                      <span className="chat__product-name">{p.name}</span>
                      <strong>{formatPrice(p.price)}</strong>
                      <span className="chat__product-stock">
                        {p.in_stock_sizes.length > 0 ? `In stock: ${p.in_stock_sizes.join(', ')}` : 'Sold out'}
                      </span>
                    </span>
                  </Link>
                ))}
              </div>
            )}
          </div>
        ))}
        {sending && (
          <div className="chat__pending" role="status" aria-live="polite">
            <span className="chat__typing" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
            {PENDING_STAGES[pendingStage].text}
          </div>
        )}
      </div>

      {productId && (
        <p className="chat__context" title="The assistant knows which product you're viewing">
          Viewing: <strong>{productName ?? 'this product'}</strong>. Ask “do you have this in…?”
        </p>
      )}

      <form className="chat__form" onSubmit={handleSubmit}>
        <textarea
          ref={inputRef}
          rows={1}
          value={draft}
          maxLength={MAX_MESSAGE_CHARS}
          placeholder={productId ? 'Ask about this product…' : 'Ask about a product…'}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleSubmit()
            }
          }}
          aria-label="Message"
        />
        <button
          type="submit"
          className="btn btn--primary btn--sm chat__send"
          disabled={!draft.trim() || sending || historyState === 'loading'}
        >
          Send
          <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
            <path fill="currentColor" d="M3.4 20.4 21 12 3.4 3.6 3.4 10l12.6 2-12.6 2z" />
          </svg>
        </button>
      </form>
    </section>
  )
}
