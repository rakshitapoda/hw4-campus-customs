import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { ChatSearchResults } from '../types'

// Kept in sessionStorage so the results survive a refresh or a trip to a product page and back.
const STORAGE_KEY = 'cc_chat_search'

/** Query-string flag that tells the Products page to show the latest chat search. */
export const CHAT_VIEW_PARAM = 'view'
export const CHAT_VIEW_VALUE = 'chat'
export const CHAT_RESULTS_PATH = `/products?${CHAT_VIEW_PARAM}=${CHAT_VIEW_VALUE}`

interface ChatSearchState {
  results: ChatSearchResults | null
  setResults: (results: ChatSearchResults) => void
  clearResults: () => void
}

const ChatSearchContext = createContext<ChatSearchState | null>(null)

function loadSaved(): ChatSearchResults | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as ChatSearchResults) : null
  } catch {
    return null
  }
}

export function ChatSearchProvider({ children }: { children: ReactNode }) {
  const [results, setResultsState] = useState<ChatSearchResults | null>(loadSaved)

  const setResults = useCallback((next: ChatSearchResults) => {
    setResultsState(next)
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      // Storage full or unavailable: results still work for this page view.
    }
  }, [])

  const clearResults = useCallback(() => {
    setResultsState(null)
    sessionStorage.removeItem(STORAGE_KEY)
  }, [])

  const value = useMemo(() => ({ results, setResults, clearResults }), [results, setResults, clearResults])
  return <ChatSearchContext.Provider value={value}>{children}</ChatSearchContext.Provider>
}

// Hook lives beside its provider; this only affects Vite fast refresh, not behavior.
// oxlint-disable-next-line react/only-export-components
export function useChatSearch(): ChatSearchState {
  const ctx = useContext(ChatSearchContext)
  if (!ctx) throw new Error('useChatSearch must be used inside <ChatSearchProvider>')
  return ctx
}
