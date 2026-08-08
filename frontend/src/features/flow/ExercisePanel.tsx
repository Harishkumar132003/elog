import { useMemo, useState } from 'react'

import { AlertIcon, ArrowIcon } from '../../components/icons'
import { submitAttempt } from '../../lib/entries'
import type { Attempt, Exercise } from '../../types'

const MIN_ANSWER_CHARS = 40

interface Props {
  entryId: string
  exercise: Exercise
  readOnly: boolean
  onMarked: (attempt: Attempt) => void
}

/** Screen 4 — every question is answered in free text, never multiple choice. */
export function ExercisePanel({ entryId, exercise, readOnly, onMarked }: Props) {
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const answered = useMemo(
    () =>
      exercise.questions.filter(
        (question) => (answers[question.id] ?? '').trim().length >= MIN_ANSWER_CHARS,
      ).length,
    [answers, exercise.questions],
  )
  const ready = answered === exercise.questions.length

  async function submit() {
    if (!ready || busy) return
    setBusy(true)
    setError(null)
    try {
      onMarked(
        await submitAttempt(
          entryId,
          exercise.questions.map((question) => ({
            question_id: question.id,
            answer: (answers[question.id] ?? '').trim(),
          })),
        ),
      )
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not submit your answers')
      setBusy(false)
    }
  }

  return (
    <section className="card exercise">
      <header className="panel-head">
        <div>
          <span className="eyebrow">Screen 4 · reason</span>
          <h2 className="panel-title">
            {readOnly ? 'The questions this case generated' : 'Your reasoning exercise'}
          </h2>
        </div>
        <span className="pill pill-accent">
          {exercise.questions.length} question{exercise.questions.length === 1 ? '' : 's'}
        </span>
      </header>

      {!readOnly && (
        <p className="certify-lede">
          Each question varies your case along one axis your professor certified. Answer in
          your own words — there is no multiple choice, and a decision without its
          justification scores nothing.
        </p>
      )}

      <ol className="questions">
        {exercise.questions.map((question) => {
          const value = answers[question.id] ?? ''
          const enough = value.trim().length >= MIN_ANSWER_CHARS
          return (
            <li
              className={`question${question.critical ? ' is-critical' : ''}`}
              key={question.id}
            >
              <div className="question-head">
                <span className="question-num">{question.id}</span>
                <div className="question-tags">
                  <span className="pill pill-warm">{question.axis_label}</span>
                  <span className="pill">COG · {question.cognitive}</span>
                  <span className="pill">AFF · {question.affective}</span>
                  <span className="pill">{question.marks} marks</span>
                  {question.critical && (
                    <span className="pill pill-alert">
                      <AlertIcon width={11} height={11} />
                      Critical
                    </span>
                  )}
                </div>
              </div>

              <p className="question-prompt prose">{question.prompt}</p>

              {!readOnly && (
                <div className="answer">
                  <textarea
                    className="answer-input prose"
                    value={value}
                    rows={5}
                    placeholder="Your decision, and what makes it the right one…"
                    aria-label={`Answer to question ${question.id}`}
                    onChange={(event) =>
                      setAnswers((current) => ({ ...current, [question.id]: event.target.value }))
                    }
                  />
                  <div className="answer-foot">
                    <span className={enough ? 'is-ok' : ''}>
                      {enough
                        ? 'ready'
                        : `${Math.max(0, MIN_ANSWER_CHARS - value.trim().length)} more characters`}
                    </span>
                  </div>
                </div>
              )}
            </li>
          )
        })}
      </ol>

      {!readOnly && (
        <footer className="panel-foot">
          <p className={`panel-status${error ? ' is-error' : ''}`}>
            {error ?? `${answered} of ${exercise.questions.length} answered`}
          </p>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!ready || busy}
            onClick={submit}
          >
            {busy ? 'Marking…' : 'Submit for marking'}
            {!busy && <ArrowIcon width={16} height={16} />}
          </button>
        </footer>
      )}
    </section>
  )
}
