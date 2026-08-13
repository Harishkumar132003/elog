import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import { listCases } from './cases'
import { listEntries, listResidents } from './entries'
import { useAuth } from './auth'
import type { AuthUser, Case, Entry } from '../types'

interface WorkspaceState {
  /** Individual logs — one per participant per case. */
  entries: Entry[]
  /** The shared cases those logs belong to. */
  cases: Case[]
  residents: AuthUser[]
  residentNames: Map<string, string>
  /** Logs still waiting on a professor to write their questions. */
  queue: Entry[]
  /** Cases with an exercise released to *you* and not yet answered. */
  toAnswer: Case[]
  loading: boolean
  /** Insert or replace one entry without refetching the whole list. */
  upsert: (entry: Entry) => void
  refresh: () => Promise<void>
}

const WorkspaceContext = createContext<WorkspaceState | null>(null)

/** Loads the lists once per session so every route shares them. */
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const isProfessor = user?.role === 'professor'

  const [entries, setEntries] = useState<Entry[]>([])
  const [cases, setCases] = useState<Case[]>([])
  const [residents, setResidents] = useState<AuthUser[]>([])
  const [loading, setLoading] = useState(true)
  const loadedAt = useRef(0)

  const refresh = useCallback(
    async (showSpinner = true) => {
      if (showSpinner) setLoading(true)
      try {
        const [page, shared, roster] = await Promise.all([
          listEntries({ limit: 100 }),
          listCases().catch(() => ({ items: [] as Case[], total: 0 })),
          isProfessor ? listResidents() : Promise.resolve([] as AuthUser[]),
        ])
        setEntries(page.items)
        setCases(shared.items)
        setResidents(roster)
        loadedAt.current = Date.now()
      } catch {
        /* the API scopes by role; a failure just leaves the lists empty */
      } finally {
        if (showSpinner) setLoading(false)
      }
    },
    [isProfessor],
  )

  useEffect(() => {
    void refresh()
  }, [refresh])

  // A case moves on when *someone else* acts on it — a professor certifies in
  // their own window while the resident's list still says "awaiting
  // certification". Re-read on focus so coming back to the tab shows the truth.
  useEffect(() => {
    const STALE_AFTER = 10_000
    const recheck = () => {
      if (document.hidden) return
      if (Date.now() - loadedAt.current < STALE_AFTER) return
      void refresh(false) // quietly — no spinner over a list already on screen
    }
    window.addEventListener('focus', recheck)
    document.addEventListener('visibilitychange', recheck)
    return () => {
      window.removeEventListener('focus', recheck)
      document.removeEventListener('visibilitychange', recheck)
    }
  }, [refresh])

  const upsert = useCallback((entry: Entry) => {
    setEntries((current) => {
      const index = current.findIndex((item) => item.id === entry.id)
      if (index === -1) return [entry, ...current]
      const next = [...current]
      next[index] = entry
      return next
    })
  }, [])

  const value = useMemo<WorkspaceState>(
    () => ({
      entries,
      cases,
      residents,
      residentNames: new Map(residents.map((r) => [r.id, r.name])),
      queue: entries.filter((entry) => entry.status === 'logged'),
      // Derived from the roster rather than from `entries`, because the roster
      // row is the only place that knows whether the exercise was released —
      // and only ever carries that for the viewer's own row.
      toAnswer: cases.filter((record) =>
        record.participants.some(
          (participant) =>
            participant.user_id === user?.id &&
            participant.released &&
            participant.status !== 'answered',
        ),
      ),
      loading,
      upsert,
      refresh,
    }),
    [entries, cases, residents, loading, upsert, refresh, user?.id],
  )

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
}

export function useWorkspace(): WorkspaceState {
  const context = useContext(WorkspaceContext)
  if (!context) throw new Error('useWorkspace must be used inside WorkspaceProvider')
  return context
}
