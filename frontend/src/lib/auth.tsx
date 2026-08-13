import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { api, clearToken, getToken, setToken, setUnauthorizedHandler } from './api'
import type { AuthUser, Identity } from '../types'

interface AuthState {
  user: AuthUser | null
  identities: Identity[]
  ready: boolean
  /** Become one of the fixed identities. This is the whole of "signing in". */
  switchTo: (key: string) => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

interface TokenResponse {
  access_token: string
  user: AuthUser
}

/** Where a first-time visitor lands. A participant rather than the professor,
 *  because the flow starts by creating a case. Mirrors the server's default. */
const DEFAULT_IDENTITY = 'independent'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [identities, setIdentities] = useState<Identity[]>([])
  const [ready, setReady] = useState(false)

  const switchTo = useCallback(async (key: string) => {
    const result = await api<TokenResponse>('/auth/switch', {
      method: 'POST',
      body: { role: key },
    })
    setToken(result.access_token)
    setUser(result.user)
  }, [])

  // A token rejected mid-session used to drop to the login screen. There is no
  // login screen now, so fall back to the default identity instead of a dead end.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      clearToken()
      void switchTo(DEFAULT_IDENTITY).catch(() => setUser(null))
    })
  }, [switchTo])

  useEffect(() => {
    let live = true

    const boot = async () => {
      // The dropdown's contents. Unauthenticated, because it is what you use to
      // get a token in the first place.
      api<Identity[]>('/auth/identities')
        .then((list) => live && setIdentities(list))
        .catch(() => undefined)

      // The token outlives the page; the user object does not. Restore it, and
      // if that fails become the default rather than showing a gate.
      try {
        if (getToken()) {
          const me = await api<AuthUser>('/auth/me')
          if (live) setUser(me)
        } else {
          await switchTo(DEFAULT_IDENTITY)
        }
      } catch {
        clearToken()
        try {
          await switchTo(DEFAULT_IDENTITY)
        } catch {
          /* the server is down; the shell will show it */
        }
      } finally {
        if (live) setReady(true)
      }
    }

    void boot()
    return () => {
      live = false
    }
  }, [switchTo])

  const value = useMemo(
    () => ({ user, identities, ready, switchTo }),
    [user, identities, ready, switchTo],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
