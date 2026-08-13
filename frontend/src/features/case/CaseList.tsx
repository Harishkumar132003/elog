import { useCallback, useState } from 'react'

import { ConfirmDialog } from '../../components/ConfirmDialog'
import { deleteCase } from '../../lib/cases'
import { EmptyState } from '../views/EmptyState'
import type { AuthUser, Case } from '../../types'
import './case.css'

const when = (value: string) =>
  new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })

interface Props {
  cases: Case[]
  user: AuthUser
  loading: boolean
  onOpen: (caseId: string) => void
  onNew?: () => void
  /** A case was removed; the list behind this is stale. */
  onDeleted: () => void
}

/** Every case this person was in. The professor sees all of them.
 *
 *  Listed by case rather than by log, because a log only makes sense beside the
 *  others on the same case — the whole point is that several people describe one
 *  event differently. */
export function CaseList({ cases, user, loading, onOpen, onNew, onDeleted }: Props) {
  /** The card awaiting confirmation. Held whole so the dialog can name it. */
  const [pending, setPending] = useState<Case | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const remove = useCallback(async () => {
    if (!pending || deleting) return
    setDeleting(true)
    setError(null)
    try {
      await deleteCase(pending.id)
      setPending(null)
      onDeleted()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not delete that case')
    } finally {
      setDeleting(false)
    }
  }, [pending, deleting, onDeleted])

  const isProfessor = user.role === 'professor'

  return (
    <>
      <header className="page-head">
        <div>
          <span className="eyebrow">{isProfessor ? 'Supervision' : 'Logbook'}</span>
          <h1 className="page-title">{isProfessor ? 'All cases' : 'Your cases'}</h1>
          <p className="case-lede">
            {isProfessor
              ? 'Every case logged across the unit. Open one to see who was in it and build their questions.'
              : 'Cases you created or were named on. Open one to add your own log.'}
          </p>
        </div>
        {onNew && (
          <button type="button" className="btn btn-primary" onClick={onNew}>
            New case
          </button>
        )}
      </header>

      {loading ? (
        <div className="case-boot">
          <div className="skeleton-card" />
          <div className="skeleton-card" />
        </div>
      ) : cases.length === 0 ? (
        <EmptyState
          title="No cases yet"
          body={
            isProfessor
              ? 'Cases appear here as soon as anyone logs one.'
              : 'Create a case, name who else was in the room, and each of you adds your own log.'
          }
          action={onNew ? { label: 'Create the first case', onClick: onNew } : undefined}
        />
      ) : (
        <ul className="case-list">
          {cases.map((record) => {
            const logged = record.participants.filter((p) => p.entry_id).length
            const mine = record.participants.find((p) => p.user_id === user.id)
            const owes = mine != null && mine.entry_id == null

            return (
              <li key={record.id} className="case-card">
                {/* Only this part opens the case. The footer holds an action of
                    its own, and a button cannot live inside a button. */}
                <button
                  type="button"
                  className="case-card-open"
                  onClick={() => onOpen(record.id)}
                >
                  <div className="case-card-top">
                    <span className="case-card-subject">{record.subject}</span>
                    <span className="case-card-date">{when(record.created_at)}</span>
                  </div>

                  <strong className="case-card-title">
                    {record.diagnosis ?? record.narrative.slice(0, 80)}
                  </strong>

                  {record.competency_title && (
                    <span className="case-card-competency">{record.competency_title}</span>
                  )}
                </button>

                <div className="case-card-foot">
                  <span className="case-card-people">
                    {record.participants.map((p) => p.role_label).join(' · ')}
                  </span>
                  <span className={`case-card-count${logged === record.participants.length ? ' is-full' : ''}`}>
                    {logged}/{record.participants.length} logged
                  </span>
                  {owes && <span className="case-card-owes">Your log is missing</span>}
                  <button
                    type="button"
                    className="case-card-delete"
                    title="Delete this case"
                    aria-label={`Delete the case: ${record.diagnosis ?? record.subject}`}
                    onClick={() => setPending(record)}
                  >
                    Delete
                  </button>
                </div>
              </li>
            )
          })}
        </ul>
      )}

      {error && <p className="entry-error">{error}</p>}

      {pending && (
        <ConfirmDialog
          danger
          busy={deleting}
          title="Delete this case?"
          lede={pending.diagnosis ?? pending.narrative.slice(0, 80)}
          points={[
            `Every log on it goes — ${pending.participants.filter((p) => p.entry_id).length} written so far.`,
            'So does everything built on those logs: the questions, the marks and the recorded results.',
            'Anyone else on this case loses their log and their exercise too.',
            'This cannot be undone.',
          ]}
          confirmLabel="Delete the case"
          cancelLabel="Keep it"
          onConfirm={() => void remove()}
          onCancel={() => setPending(null)}
        />
      )}
    </>
  )
}
