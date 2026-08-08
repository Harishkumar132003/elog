import { memo } from 'react'
import { NavLink } from 'react-router-dom'

import type { AuthUser, UserRole } from '../types'
import { BookIcon, ChartIcon, GearIcon, GridIcon, NodeIcon, PenIcon, SlidersIcon } from './icons'
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

const initials = (name: string) =>
  name
    .replace(/^(Dr|Prof)\.?\s+/i, '')
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()

interface SidebarProps {
  user: AuthUser
  onLogout: () => void
  logged: number
  target: number
  awaiting: number
}

function SidebarBase({ user, onLogout, logged, target, awaiting }: SidebarProps) {
  const isResident = user.role === 'resident'
  const pct = Math.min(100, Math.round((logged / target) * 100))

  const allGroups: NavGroup[] = [
    {
      title: isResident ? 'Logbook' : 'Supervision',
      shown: true,
      items: [
        { to: '/new', label: 'New entry', icon: PenIcon, roles: ['resident'] },
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
      <div className="rail-brand">
        <span className="rail-mark" aria-hidden>
          O
        </span>
        <span className="rail-brand-text">
          <strong>OpBook360</strong>
          <small>Formative reasoning</small>
        </span>
      </div>

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

      <div className="rail-foot">
        <NavLink
          to="/settings"
          className={({ isActive }) => `rail-item${isActive ? ' is-active' : ''}`}
        >
          <GearIcon className="rail-icon" />
          <span>Settings</span>
        </NavLink>

        <div className="rail-user">
          <span className="rail-avatar" aria-hidden>
            {initials(user.name)}
          </span>
          <span className="rail-user-text">
            <strong>{user.name}</strong>
            <small>
              {isResident
                ? `Year ${user.year ?? '—'} · ${user.department ?? ''}`
                : (user.department ?? 'Faculty')}
            </small>
          </span>
          <button type="button" className="rail-signout" onClick={onLogout} title="Sign out">
            Exit
          </button>
        </div>
      </div>
    </aside>
  )
}

export const Sidebar = memo(SidebarBase)
