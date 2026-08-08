import { useState, type FormEvent } from 'react'

import { ArrowIcon } from '../../components/icons'
import { ApiError } from '../../lib/api'
import { useAuth } from '../../lib/auth'
import './login.css'

const DEMO = [
  { label: 'Resident', email: 'resident@opbook360.ai' },
  { label: 'Professor', email: 'prof.rao@opbook360.ai' },
]
const DEMO_PASSWORD = 'opbook360'

export function LoginScreen() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email.trim(), password)
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Could not sign in')
      setBusy(false)
    }
  }

  function useDemo(demoEmail: string) {
    setEmail(demoEmail)
    setPassword(DEMO_PASSWORD)
    setError(null)
  }

  return (
    <div className="login">
      <div className="login-panel">
        <div className="login-brand">
          <span className="login-mark" aria-hidden>
            o
          </span>
          <span>
            <strong>OpBook360</strong>
            <small>Formative reasoning</small>
          </span>
        </div>

        <h1 className="login-title">Sign in</h1>
        <p className="login-sub">
          Your logbook entries and the reasoning built from them.
        </p>

        <form className="login-form" onSubmit={submit}>
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              value={email}
              autoComplete="username"
              required
              autoFocus
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>

          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              autoComplete="current-password"
              required
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>

          {error && (
            <p className="login-error" role="alert">
              {error}
            </p>
          )}

          <button type="submit" className="btn btn-primary login-submit" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
            {!busy && <ArrowIcon width={16} height={16} />}
          </button>
        </form>

        <div className="login-demo">
          <span className="eyebrow">Demo accounts</span>
          <div className="login-demo-row">
            {DEMO.map((account) => (
              <button
                key={account.email}
                type="button"
                className="btn btn-quiet"
                onClick={() => useDemo(account.email)}
              >
                {account.label}
              </button>
            ))}
          </div>
          <p className="login-demo-note">
            Fills the form with a seeded account · password <code>{DEMO_PASSWORD}</code>
          </p>
        </div>
      </div>
    </div>
  )
}
