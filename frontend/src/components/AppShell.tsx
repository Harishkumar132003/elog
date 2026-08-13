import { Outlet } from 'react-router-dom'

import { useAuth } from '../lib/auth'
import { useWorkspace } from '../lib/workspace'
import { Header } from './Header'
import { Sidebar } from './Sidebar'

const WEEKLY_TARGET = 10

/** The persistent chrome every route renders inside.
 *
 *  The header spans the full width above both the rail and the page: identity
 *  belongs to neither, it is the frame both sit inside. */
export function AppShell() {
  const { user } = useAuth()
  const { entries, queue, toAnswer } = useWorkspace()

  if (!user) return null

  return (
    <div className="frame">
      <Header />
      <div className="shell">
        <Sidebar
          user={user}
          logged={entries.length}
          target={WEEKLY_TARGET}
          awaiting={queue.length}
          pending={toAnswer.length}
        />
        <main className="main">
          <div className="main-inner">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
