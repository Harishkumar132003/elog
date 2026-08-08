import { Outlet } from 'react-router-dom'

import { useAuth } from '../lib/auth'
import { useWorkspace } from '../lib/workspace'
import { Sidebar } from './Sidebar'

const WEEKLY_TARGET = 10

/** The persistent chrome every signed-in route renders inside. */
export function AppShell() {
  const { user, logout } = useAuth()
  const { entries, queue } = useWorkspace()

  if (!user) return null

  return (
    <div className="shell">
      <Sidebar
        user={user}
        onLogout={logout}
        logged={entries.length}
        target={WEEKLY_TARGET}
        awaiting={queue.length}
      />
      <main className="main">
        <div className="main-inner">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
