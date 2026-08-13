import { memo } from 'react'
import { NavLink } from 'react-router-dom'

import type { AuthUser, UserRole } from '../types'
import { BookIcon, ChartIcon, GridIcon, NodeIcon, PenIcon, SlidersIcon } from './icons'
import './sidebar.css'

interface NavItem {
  to: string
  label: string
  icon: typeof PenIcon
  roles: UserRole[]
  badge?: number
}

interface NavGroup {
  title: string
  items: NavItem[]
  /** Built but not exposed — set true to bring the group back into the nav. */
  shown?: boolean
}

/** Built but not exposed — set true to bring the weekly meter back. */
const SHOW_WEEKLY_METER = false

interface SidebarProps {
  user: AuthUser
  logged: number
  target: number
  /** Logs waiting on the professor to write questions. */
  awaiting: number
  /** Exercises released to this participant and not yet answered. */
  pending: number
}

function SidebarBase({ user, logged, target, awaiting, pending }: SidebarProps) {
  const isResident = user.role === 'resident'
  const pct = Math.min(100, Math.round((logged / target) * 100))

  const allGroups: NavGroup[] = [
    {
      title: isResident ? 'Logbook' : 'Supervision',
      shown: true,
      items: [
        { to: '/cases/new', label: 'New case', icon: PenIcon, roles: ['resident'] },
        {
          to: '/to-answer',
          label: 'To answer',
          icon: NodeIcon,
          roles: ['resident'],
          badge: pending || undefined,
        },
        { to: '/dashboard', label: 'Dashboard', icon: ChartIcon, roles: ['professor'] },
        { to: '/residents', label: 'My residents', icon: GridIcon, roles: ['professor'] },
        {
          to: '/queue',
          label: 'To certify',
          icon: NodeIcon,
          roles: ['professor'],
          badge: awaiting || undefined,
        },
        { to: '/cases', label: 'All cases', icon: BookIcon, roles: ['resident', 'professor'] },
      ],
    },
    {
      title: 'Setup',
      shown: true,
      items: [
        {
          to: '/configuration',
          label: 'Configuration',
          icon: SlidersIcon,
          roles: ['professor'],
        },
      ],
    },
    {
      title: 'Framework',
      items: [
        {
          to: '/reference',
          label: 'Axes & domains',
          icon: ChartIcon,
          roles: ['resident', 'professor'],
        },
      ],
    },
  ]

  const groups = allGroups
    .filter((group) => group.shown)
    .map((group) => ({ ...group, items: group.items.filter((i) => i.roles.includes(user.role)) }))
    .filter((group) => group.items.length > 0)

  return (
    <aside className="rail">
      {/* The brand lives in the header now — the rail starts at the nav. */}
      <nav className="rail-nav" aria-label="Main">
        {groups.map((group) => (
          <div className="rail-group" key={group.title}>
            <p className="rail-group-title">{group.title}</p>
            <ul>
              {group.items.map(({ to, label, icon: Icon, badge }) => (
                <li key={to}>
                  <NavLink
                    to={to}
                    className={({ isActive }) => `rail-item${isActive ? ' is-active' : ''}`}
                  >
                    <Icon className="rail-icon" />
                    <span>{label}</span>
                    {badge ? <em className="rail-count">{badge}</em> : null}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      {SHOW_WEEKLY_METER && isResident && (
        <div className="rail-meter">
          <div className="rail-meter-head">
            <span>This week</span>
            <strong>
              {logged}/{target}
            </strong>
          </div>
          <div className="rail-meter-track">
            <div className="rail-meter-fill" style={{ width: `${pct}%` }} />
          </div>
          <p className="rail-meter-note">Cases logged towards your weekly minimum</p>
        </div>
      )}

      {/* No sign-out and no user card: identity is the header's dropdown, and
          there is nothing to sign out of. */}
    </aside>
  )
}

export const Sidebar = memo(SidebarBase)
