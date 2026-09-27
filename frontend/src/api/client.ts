import type {
  AuthResponse,
  ChatHistoryResponse,
  ChatResponse,
  ChatTurn,
  PageContext,
  ProductDetail,
  ProductSummary,
  PublicUser,
} from '../types'

// Relative URLs: Vite proxies /api and /media to the backend in development.
const API_BASE = '/api'

/** What went wrong, so the UI can show the right message and offer the right action. */
export type ApiErrorKind = 'offline' | 'timeout' | 'network' | 'rate_limited' | 'not_found' | 'client' | 'server'

export class ApiError extends Error {
  status: number
  kind: ApiErrorKind
  /** Backend request id (X-Request-ID), shown as a reference on server errors. */
  requestId: string | null

  constructor(status: number, message: string, kind: ApiErrorKind, requestId: string | null = null) {
    super(message)
    this.status = status
    this.kind = kind
    this.requestId = requestId
  }

  /** Worth offering a "Try again" button? */
  get retryable(): boolean {
    return ['offline', 'timeout', 'network', 'rate_limited', 'server'].includes(this.kind)
  }
}

const DEFAULT_TIMEOUT_MS = 15_000
export const CHAT_TIMEOUT_MS = 75_000 // backend allows the agent 60s (CHAT_TIMEOUT_SECONDS)

function kindForStatus(status: number): ApiErrorKind {
  if (status === 404) return 'not_found'
  if (status === 429) return 'rate_limited'
  if (status >= 500) return 'server'
  return 'client'
}

async function request<T>(
  path: string,
  init?: RequestInit,
  token?: string | null,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers.Authorization = `Bearer ${token}`

  // Abort on timeout, or when the caller's signal aborts (e.g. the page unmounted).
  const controller = new AbortController()
  const callerSignal = init?.signal
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)
  const onCallerAbort = () => controller.abort()
  callerSignal?.addEventListener('abort', onCallerAbort)

  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers, signal: controller.signal })
  } catch (err) {
    if (callerSignal?.aborted) throw err // caller cancelled on purpose: not an error to show
    if (timedOut) {
      throw new ApiError(0, 'This is taking longer than expected. Please check your connection and try again.', 'timeout')
    }
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      throw new ApiError(0, 'You appear to be offline. Reconnect to the internet and try again.', 'offline')
    }
    throw new ApiError(0, 'We couldn’t reach the Campus Customs server. Please try again in a moment.', 'network')
  } finally {
    clearTimeout(timer)
    callerSignal?.removeEventListener('abort', onCallerAbort)
  }

  if (!res.ok) {
    // The backend always returns {"detail": "<readable message>", "request_id": "..."} for errors.
    const body = await res.json().catch(() => null)
    const requestId = (typeof body?.request_id === 'string' && body.request_id) || res.headers.get('X-Request-ID')
    let detail = typeof body?.detail === 'string' ? body.detail : ''
    if (!detail) {
      detail = res.status >= 500
        ? 'Something went wrong on our side. Please try again in a moment.'
        : `The request couldn’t be completed (error ${res.status}).`
    }
    throw new ApiError(res.status, detail, kindForStatus(res.status), requestId)
  }
  return res.json() as Promise<T>
}

export function fetchProducts(signal?: AbortSignal): Promise<ProductSummary[]> {
  return request<ProductSummary[]>('/products', { signal })
}

export function fetchProduct(productId: string, signal?: AbortSignal): Promise<ProductDetail> {
  return request<ProductDetail>(`/products/${encodeURIComponent(productId)}`, { signal })
}

// Answered by the PydanticAI agent (backend/agent.py).
// - Logged in (token): the server loads and saves history itself, so `history` is ignored.
// - Guest: `history` (this tab's turns) gives the agent short-term memory; nothing is stored.
// - pageContext tells the agent which page/product the shopper is looking at.
export function sendChatMessage(
  message: string,
  history: ChatTurn[],
  token: string | null,
  pageContext: PageContext,
): Promise<ChatResponse> {
  return request<ChatResponse>(
    '/chat',
    { method: 'POST', body: JSON.stringify({ message, history, page_context: pageContext }) },
    token,
    CHAT_TIMEOUT_MS,
  )
}

export function fetchChatHistory(token: string): Promise<ChatHistoryResponse> {
  return request<ChatHistoryResponse>('/chat/history', undefined, token)
}

export function clearChatHistory(token: string): Promise<{ deleted: number }> {
  return request<{ deleted: number }>('/chat/history', { method: 'DELETE' }, token)
}

// ---------- Auth ----------

export interface SignupInput {
  first_name: string
  last_name: string
  email: string
  password: string
  confirm_password: string
}

export function signup(input: SignupInput): Promise<AuthResponse> {
  return request<AuthResponse>('/auth/signup', { method: 'POST', body: JSON.stringify(input) })
}

export function login(email: string, password: string): Promise<AuthResponse> {
  return request<AuthResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
}

export function fetchCurrentUser(token: string): Promise<PublicUser> {
  return request<PublicUser>('/auth/me', undefined, token)
}
