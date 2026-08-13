import { useEffect, useRef, useState } from 'react'

import { useAuth } from '../lib/auth'
import './header.css'

const initials = (name: string) =>
  name
    .replace(/^(Dr|Prof)\.?\s+/i, '')
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()

/** Who you are, and how you become someone else.
 *
 *  There is no sign-in: name and role are the same thing here, so this dropdown
 *  is the whole of authentication. Switching mints a new token and reloads the
 *  workspace, which is why it is a full page navigation rather than a state
 *  change — every list on screen belongs to the person who was looking at it. */
export function Header() {
  const { user, identities, switchTo } = useAuth()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const menu = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const away = (event: MouseEvent) => {
      if (menu.current && !menu.current.contains(event.target as Node)) setOpen(false)
    }
    const escape = (event: KeyboardEvent) => event.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', away)
      document.removeEventListener('keydown', escape)
    }
  }, [open])

  if (!user) return null

  const current = identities.find((identity) => identity.name === user.name)

  const become = async (key: string) => {
    if (busy || key === current?.key) {
      setOpen(false)
      return
    }
    setBusy(key)
    try {
      await switchTo(key)
      // Everything on screen — cases, logs, the queue — was fetched as the
      // previous person. Land on the root so each role starts where it should.
      window.location.assign('/')
    } catch {
      setBusy(null)
      setOpen(false)
    }
  }

  return (
    <header className="topbar">
      <div className="topbar-inner">
        <div className="topbar-brand">
          <span className="topbar-mark" aria-hidden>
            O
          </span>
          <span className="topbar-brand-text">
            <strong>OpBook360</strong>
            <small>Formative reasoning</small>
          </span>
        </div>

        <div className="topbar-identity" ref={menu}>
          <span className="topbar-label">Viewing as</span>
          <button
            type="button"
            className={`identity-trigger${open ? ' is-open' : ''}`}
            aria-haspopup="listbox"
            aria-expanded={open}
            onClick={() => setOpen((on) => !on)}
          >
            <span className="identity-avatar" aria-hidden>
              {initials(user.name)}
            </span>
            <span className="identity-text">
              <strong>{user.name}</strong>
              <small>{user.role === 'professor' ? 'Sets the questions' : 'Works cases'}</small>
            </span>
            <svg className="identity-caret" width="12" height="12" viewBox="0 0 12 12" aria-hidden>
              <path
                d="M2.5 4.5 6 8l3.5-3.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>

          {open && (
            <div className="identity-menu" role="listbox" aria-label="Switch identity">
              <p className="identity-menu-head">There is no sign-in — pick who you are</p>
              {identities.map((identity) => (
                <button
                  key={identity.key}
                  type="button"
                  role="option"
                  aria-selected={identity.key === current?.key}
                  className={`identity-option${identity.key === current?.key ? ' is-on' : ''}`}
                  disabled={busy !== null}
                  onClick={() => void become(identity.key)}
                >
                  <span className="identity-avatar" aria-hidden>
                    {initials(identity.name)}
                  </span>
                  <span className="identity-text">
                    <strong>{identity.name}</strong>
                    <small>
                      {identity.role === 'professor'
                        ? 'Builds the questions, cannot create a case'
                        : 'Creates and logs cases'}
                    </small>
                  </span>
                  {busy === identity.key && <span className="identity-busy">…</span>}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
