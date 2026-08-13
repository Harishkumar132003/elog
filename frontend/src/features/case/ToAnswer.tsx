import { ArrowIcon } from '../../components/icons'
import { EmptyState } from '../views/EmptyState'
import type { AuthUser, Case } from '../../types'
import './case.css'

const when = (value: string | null) =>
  value
    ? new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
    : null

interface Props {
  cases: Case[]
  user: AuthUser
  loading: boolean
  onAnswer: (entryId: string) => void
  onOpenCase: (caseId: string) => void
}

/** Everything released to you and not yet answered.
 *
 *  A participant's own list is otherwise sorted by when they logged, which is
 *  the wrong order for the one question that matters here — what is waiting on
 *  me? A released exercise is the only thing in this app that is genuinely
 *  outstanding, so it gets its own place rather than a badge inside a longer
 *  list.
 */
export function ToAnswer({ cases, user, loading, onAnswer, onOpenCase }: Props) {
  return (
    <>
      <header className="page-head">
        <div>
          <span className="eyebrow">Waiting on you</span>
          <h1 className="page-title">To answer</h1>
          <p className="case-lede">
            {cases.length === 0
              ? 'Reasoning exercises appear here once your professor releases them.'
              : `${cases.length} reasoning exercise${cases.length === 1 ? '' : 's'} released to you and not yet answered.`}
          </p>
        </div>
      </header>

      {loading ? (
        <div className="case-boot">
          <div className="skeleton-card" />
        </div>
      ) : cases.length === 0 ? (
        <EmptyState
          title="Nothing waiting"
          body="When your professor releases the questions on one of your logs, it will appear here."
        />
      ) : (
        <ul className="answer-list">
          {cases.map((record) => {
            const mine = record.participants.find((p) => p.user_id === user.id)
            if (!mine?.entry_id) return null

            return (
              <li key={record.id} className="answer-row">
                <div className="answer-row-text">
                  <span className="answer-row-meta">
                    {record.subject} · your role: {mine.role_label}
                    {mine.logged_at ? ` · logged ${when(mine.logged_at)}` : ''}
                  </span>
                  <strong>{record.diagnosis ?? record.narrative.slice(0, 70)}</strong>
                  {record.competency_title && (
                    <span className="answer-row-competency">{record.competency_title}</span>
                  )}
                </div>

                <div className="answer-row-actions">
                  <span className="answer-row-count">
                    {mine.questions} question{mine.questions === 1 ? '' : 's'}
                  </span>
                  <button
                    type="button"
                    className="btn btn-quiet btn-sm"
                    onClick={() => onOpenCase(record.id)}
                  >
                    The case
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    onClick={() => onAnswer(mine.entry_id as string)}
                  >
                    Answer
                    <ArrowIcon width={14} height={14} />
                  </button>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </>
  )
}
