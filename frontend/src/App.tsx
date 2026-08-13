import { type ReactNode, useCallback } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom'

import { AppShell } from './components/AppShell'
import { CaseList } from './features/case/CaseList'
import { CasePage } from './features/case/CasePage'
import { NewCase } from './features/case/NewCase'
import { ToAnswer } from './features/case/ToAnswer'
import { Configuration } from './features/config/Configuration'
import { Dashboard } from './features/dashboard/Dashboard'
import { CaseFlow } from './features/flow/CaseFlow'
import { ExercisePage } from './features/flow/ExercisePage'
import { QuestionBuilder } from './features/flow/QuestionBuilder'
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

/** Everything renders inside this: workspace data plus the shell.
 *
 *  There is no signed-out state any more — the auth provider adopts a default
 *  identity when there is no token — so this waits for boot rather than
 *  redirecting to a login screen. */
function RequireAuth() {
  const { user, ready } = useAuth()

  if (!ready) return <div className="boot" />
  if (!user) {
    return (
      <div className="boot boot-failed">
        <p>Could not reach the server. Refresh once it is back.</p>
      </div>
    )
  }

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

/** `/` has no page of its own — each role starts somewhere different. */
function HomeRedirect() {
  const { user } = useAuth()
  return <Navigate to={user?.role === 'professor' ? '/dashboard' : '/cases'} replace />
}

/** "Back" that actually returns where you came from.
 *
 *  A hardcoded destination is wrong as soon as a page has two ways in — the
 *  exercise page is reached from the builder AND from the case roster, and
 *  sending both to the case list stranded whoever came from the builder.
 *
 *  React Router stamps an `idx` on history state, so `idx > 0` means there is
 *  somewhere of ours to go back to. On a cold load — a pasted link, a new tab —
 *  there is not, and the fallback is the only sane destination.
 */
function useGoBack(fallback: string) {
  const navigate = useNavigate()
  return useCallback(() => {
    const idx = (window.history.state as { idx?: number } | null)?.idx
    if (typeof idx === 'number' && idx > 0) navigate(-1)
    else navigate(fallback)
  }, [navigate, fallback])
}

/* ── routes ────────────────────────────────────────────────────────────── */

function NewCaseRoute() {
  const navigate = useNavigate()
  return <NewCase onCreated={(record) => navigate(`/cases/${record.id}`)} />
}

function CasePageRoute() {
  const { caseId } = useParams<{ caseId: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const { refresh } = useWorkspace()

  if (!user) return null
  if (!caseId) return <Navigate to="/cases" replace />

  return (
    <CasePage
      key={caseId}
      caseId={caseId}
      user={user}
      onChanged={() => void refresh()}
      onOpenLog={(entryId) => navigate(`/cases/${caseId}/logs/${entryId}`)}
      onBuild={(entryId) => navigate(`/cases/${caseId}/logs/${entryId}/questions`)}
      onAnswer={(entryId) => navigate(`/cases/${caseId}/logs/${entryId}/exercise`)}
    />
  )
}

function QuestionBuilderRoute() {
  const { caseId, entryId } = useParams<{ caseId: string; entryId: string }>()
  const navigate = useNavigate()
  if (!entryId) return <Navigate to="/cases" replace />

  // `log` is the placeholder a log reached from the queue carries — there is no
  // case to go back to, so fall through to the list.
  const back = caseId && caseId !== 'log' ? `/cases/${caseId}` : '/cases'
  return (
    <QuestionBuilder
      key={entryId}
      entryId={entryId}
      onDone={() => navigate(back)}
      // Keep the case in the path. Dropping it left the exercise page with no
      // way to know where it came from, so its Back went to the case list.
      onPreview={() => navigate(`/cases/${caseId ?? 'log'}/logs/${entryId}/exercise`)}
    />
  )
}

/** The exercise itself — read by the professor, answered by the participant. */
function ExerciseRoute() {
  const { caseId, entryId } = useParams<{ caseId?: string; entryId: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const { refresh } = useWorkspace()
  const goBack = useGoBack(caseId && caseId !== 'log' ? `/cases/${caseId}` : '/cases')

  if (!user) return null
  if (!entryId) return <Navigate to="/cases" replace />

  return (
    <ExercisePage
      key={entryId}
      entryId={entryId}
      user={user}
      onBack={() => {
        void refresh()
        goBack()
      }}
      // Straight back to writing, without going through the case page.
      onAddMore={() => navigate(`/cases/${caseId ?? 'log'}/logs/${entryId}/questions`)}
      onOpenCase={caseId && caseId !== 'log' ? () => navigate(`/cases/${caseId}`) : undefined}
    />
  )
}

function ToAnswerRoute() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const { toAnswer, loading } = useWorkspace()
  if (!user) return null

  return (
    <ToAnswer
      cases={toAnswer}
      user={user}
      loading={loading}
      onAnswer={(entryId) => navigate(`/logs/${entryId}/exercise`)}
      onOpenCase={(caseId) => navigate(`/cases/${caseId}`)}
    />
  )
}

function CasesRoute() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const { cases, loading } = useWorkspace()
  if (!user) return null

  return (
    <CaseList
      cases={cases}
      user={user}
      loading={loading}
      onOpen={(caseId) => navigate(`/cases/${caseId}`)}
      onNew={user.role === 'resident' ? () => navigate('/cases/new') : undefined}
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
      title="Awaiting your questions"
      blurb={`${queue.length} log${queue.length === 1 ? '' : 's'} waiting for you to write its reasoning questions.`}
      // Already one stage by definition, so the tabs would be noise here.
      showStageFilter={false}
      onOpen={(entryId) => navigate(`/logs/${entryId}`)}
    />
  )
}

/** One participant's log, with whatever stage it has reached. */
function LogRoute() {
  const { caseId, entryId } = useParams<{ caseId?: string; entryId: string }>()
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
      onBack={() => navigate(caseId ? `/cases/${caseId}` : '/cases')}
      onChanged={upsert}
      // A log reached directly (from the queue) has no case in the URL; the
      // builder only needs the entry, so the case segment is cosmetic.
      onBuild={(id) => navigate(`/cases/${caseId ?? 'log'}/logs/${id}/questions`)}
      onAnswer={(id) => navigate(`/cases/${caseId ?? 'log'}/logs/${id}/exercise`)}
    />
  )
}

function ResidentsRoute() {
  const { residents, entries, loading } = useWorkspace()
  return <Residents residents={residents} entries={entries} loading={loading} />
}

function SettingsRoute() {
  const { user } = useAuth()
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
        body={`Viewing as ${user.name} · ${user.role}. Switch identity from the header. Weekly targets and Annexure I export will live here.`}
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
          <Route element={<RequireAuth />}>
            <Route index element={<HomeRedirect />} />

            <Route
              path="cases/new"
              element={
                <RequireRole role="resident">
                  <NewCaseRoute />
                </RequireRole>
              }
            />
            <Route path="cases" element={<CasesRoute />} />
            <Route
              path="to-answer"
              element={
                <RequireRole role="resident">
                  <ToAnswerRoute />
                </RequireRole>
              }
            />
            <Route path="cases/:caseId" element={<CasePageRoute />} />
            <Route
              path="cases/:caseId/logs/:entryId/questions"
              element={
                <RequireRole role="professor">
                  <QuestionBuilderRoute />
                </RequireRole>
              }
            />
            <Route path="cases/:caseId/logs/:entryId/exercise" element={<ExerciseRoute />} />
            <Route path="cases/:caseId/logs/:entryId" element={<LogRoute />} />
            <Route path="logs/:entryId/exercise" element={<ExerciseRoute />} />
            <Route path="logs/:entryId" element={<LogRoute />} />

            <Route
              path="dashboard"
              element={
                <RequireRole role="professor">
                  <Dashboard />
                </RequireRole>
              }
            />
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
