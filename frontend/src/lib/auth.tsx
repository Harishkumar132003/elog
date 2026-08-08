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
import type { AuthUser } from '../types'

interface AuthState {
  user: AuthUser | null
  ready: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthState | null>(null)

interface TokenResponse {
  access_token: string
  user: AuthUser
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [ready, setReady] = useState(false)

  const logout = useCallback(() => {
    clearToken()
    setUser(null)
  }, [])

  // A token rejected mid-session drops us straight back to the login screen.
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
  }, [])

  // Restore the session on load: the token outlives the page, the user object does not.
  useEffect(() => {
    if (!getToken()) {
      setReady(true)
      return
    }
    api<AuthUser>('/auth/me')
      .then(setUser)
      .catch(() => clearToken())
      .finally(() => setReady(true))
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const result = await api<TokenResponse>('/auth/login', {
      method: 'POST',
      body: { email, password },
    })
    setToken(result.access_token)
    setUser(result.user)
  }, [])

  const value = useMemo(() => ({ user, ready, login, logout }), [user, ready, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
