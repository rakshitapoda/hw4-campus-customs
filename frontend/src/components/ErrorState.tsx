import { ApiError } from '../api/client'

interface Props {
  error: unknown
  /** Heading, e.g. "We couldn’t load products". */
  title: string
  onRetry?: () => void
  compact?: boolean
}

const ICONS: Record<string, string> = {
  offline: '📡',
  timeout: '⏱',
  network: '🔌',
  rate_limited: '✋',
  not_found: '🔍',
  server: '⚠️',
  client: '⚠️',
}

/** A clear, consistent error panel: what happened, what to do, and a Try again button when useful. */
export default function ErrorState({ error, title, onRetry, compact = false }: Props) {
  const api = error instanceof ApiError ? error : null
  const message = api?.message ?? 'Something unexpected happened. Please try again.'
  const canRetry = Boolean(onRetry) && (api ? api.retryable : true)

  return (
    <div className={`error-state ${compact ? 'error-state--compact' : ''}`} role="alert">
      <span className="error-state__icon" aria-hidden="true">
        {ICONS[api?.kind ?? 'server']}
      </span>
      <div className="error-state__body">
        <p className="error-state__title">{title}</p>
        <p className="error-state__message">{message}</p>
        {api?.requestId && api.kind === 'server' && (
          <p className="error-state__ref">Reference: {api.requestId}</p>
        )}
      </div>
      {canRetry && (
        <button type="button" className="btn btn--primary btn--sm" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}
