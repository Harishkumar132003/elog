import { useEffect, type ReactNode } from 'react'
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from 'react-router-dom'

import { AppShell } from './components/AppShell'
import { LoginScreen } from './features/auth/LoginScreen'
import { Configuration } from './features/config/Configuration'
import { Dashboard } from './features/dashboard/Dashboard'
import { NewEntry } from './features/entry/NewEntry'
import { CaseFlow } from './features/flow/CaseFlow'
import { EmptyState } from './features/views/EmptyState'
import { Logbook } from './features/views/Logbook'
import { Reference } from './features/views/Reference'
import { Residents } from './features/views/Residents'
import './features/views/views.css'
import { AuthProvider, useAuth } from './lib/auth'
import { WorkspaceProvider, useWorkspace } from './lib/workspace'
import type { UserRole } from './types'
import './app.css'

/* ── guards ────────────────────────────────────────────────────────────── */

/** Everything signed-in renders inside this: workspace data plus the shell. */
function RequireAuth() {
  const { user, ready } = useAuth()
  const location = useLocation()

  if (!ready) return <div className="boot" />
  // Remember where they were headed so login can return them to it.
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />

  return (
    <WorkspaceProvider>
      <AppShell />
    </WorkspaceProvider>
  )
}

function RequireRole({ role, children }: { role: UserRole; children: ReactNode }) {
  const { user } = useAuth()
  if (user && user.role !== role) return <Navigate to="/" replace />
  return <>{children}</>
}

function LoginRoute() {
  const { user, ready } = useAuth()
  const location = useLocation() as { state?: { from?: { pathname: string } } }

  if (!ready) return <div className="boot" />
  if (user) return <Navigate to={location.state?.from?.pathname ?? '/'} replace />
  return <LoginScreen />
}

/** `/` has no page of its own — each role starts somewhere different. */
function HomeRedirect() {
  const { user } = useAuth()
  return <Navigate to={user?.role === 'professor' ? '/dashboard' : '/new'} replace />
}

/* ── routes ────────────────────────────────────────────────────────────── */

function NewEntryRoute() {
  const navigate = useNavigate()
  const { upsert } = useWorkspace()

  // `n` jumps to a fresh entry — but never while the resident is writing.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'n' || event.metaKey || event.ctrlKey || event.altKey) return
      const target = event.target as HTMLElement | null
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return
      navigate('/new')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navigate])

  return (
    <NewEntry
      onSaved={(entry) => {
        upsert(entry)
        navigate(`/cases/${entry.id}`)
      }}
    />
  )
}

function CasesRoute() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const { entries, residentNames, loading } = useWorkspace()
  if (!user) return null

  return (
    <Logbook
      entries={entries}
      residentNames={residentNames}
      user={user}
      loading={loading}
      onOpen={(entryId) => navigate(`/cases/${entryId}`)}
      onNew={user.role === 'resident' ? () => navigate('/new') : undefined}
    />
  )
}

function QueueRoute() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const { queue, residentNames, loading } = useWorkspace()
  if (!user) return null

  return (
    <Logbook
      entries={queue}
      residentNames={residentNames}
      user={user}
      loading={loading}
      eyebrow="Supervision"
      title="Awaiting your certification"
      blurb={`${queue.length} case${queue.length === 1 ? '' : 's'} waiting for you to certify which variations discriminate.`}
      // Already one stage by definition, so the tabs would be noise here.
      showStageFilter={false}
      onOpen={(entryId) => navigate(`/cases/${entryId}`)}
    />
  )
}

function CaseRoute() {
  const { entryId } = useParams<{ entryId: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const { upsert } = useWorkspace()

  if (!user) return null
  if (!entryId) return <Navigate to="/cases" replace />

  return (
    <CaseFlow
      key={entryId}
      entryId={entryId}
      user={user}
      onBack={() => navigate('/cases')}
      onChanged={upsert}
    />
  )
}

function ResidentsRoute() {
  const { residents, entries, loading } = useWorkspace()
  return <Residents residents={residents} entries={entries} loading={loading} />
}

function SettingsRoute() {
  const { user, logout } = useAuth()
  if (!user) return null
  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Account</span>
          <h1 className="page-title">Settings</h1>
        </div>
      </div>
      <EmptyState
        title={user.name}
        body={`Signed in as ${user.email} · ${user.role}. Weekly targets and Annexure I export will live here.`}
        action={{ label: 'Sign out', onClick: logout }}
      />
    </>
  )
}

function NotFound() {
  const navigate = useNavigate()
  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">404</span>
          <h1 className="page-title">Page not found</h1>
        </div>
      </div>
      <EmptyState
        title="That page does not exist"
        body="The link may be out of date, or the case may belong to someone else."
        action={{ label: 'Back to your cases', onClick: () => navigate('/cases') }}
      />
    </>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginRoute />} />

          <Route element={<RequireAuth />}>
            <Route index element={<HomeRedirect />} />
            <Route
              path="new"
              element={
                <RequireRole role="resident">
                  <NewEntryRoute />
                </RequireRole>
              }
            />
            <Route
              path="dashboard"
              element={
                <RequireRole role="professor">
                  <Dashboard />
                </RequireRole>
              }
            />
            <Route path="cases" element={<CasesRoute />} />
            <Route path="cases/:entryId" element={<CaseRoute />} />
            <Route
              path="queue"
              element={
                <RequireRole role="professor">
                  <QueueRoute />
                </RequireRole>
              }
            />
            <Route
              path="residents"
              element={
                <RequireRole role="professor">
                  <ResidentsRoute />
                </RequireRole>
              }
            />
            <Route
              path="configuration"
              element={
                <RequireRole role="professor">
                  <Configuration />
                </RequireRole>
              }
            />
            <Route path="reference" element={<Reference />} />
            <Route path="settings" element={<SettingsRoute />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
