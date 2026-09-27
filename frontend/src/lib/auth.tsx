import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { ApiError, fetchCurrentUser } from '../api/client'
import type { AuthResponse, PublicUser } from '../types'

const TOKEN_KEY = 'cc_session'

interface AuthState {
  user: PublicUser | null
  token: string | null
  /** True while a saved session is being checked with the backend on page load. */
  restoring: boolean
  signIn: (res: AuthResponse) => void
  signOut: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY))
  const [user, setUser] = useState<PublicUser | null>(null)
  const [restoring, setRestoring] = useState<boolean>(() => localStorage.getItem(TOKEN_KEY) !== null)

  // Re-validate a saved session with the backend so an expired or forged token is discarded.
  useEffect(() => {
    const saved = localStorage.getItem(TOKEN_KEY)
    if (!saved) return
    fetchCurrentUser(saved)
      .then(setUser)
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 401) {
          localStorage.removeItem(TOKEN_KEY)
          setToken(null)
        }
      })
      .finally(() => setRestoring(false))
  }, [])

  const signIn = useCallback((res: AuthResponse) => {
    localStorage.setItem(TOKEN_KEY, res.token)
    setToken(res.token)
    setUser(res.user)
  }, [])

  const signOut = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({ user, token, restoring, signIn, signOut }),
    [user, token, restoring, signIn, signOut],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// Hook lives beside its provider; this only affects Vite fast refresh, not behavior.
// oxlint-disable-next-line react/only-export-components
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
