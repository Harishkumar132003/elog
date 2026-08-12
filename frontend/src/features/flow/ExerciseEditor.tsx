import { useMemo, useState } from 'react'

import { AiIcon, AlertIcon, ArrowIcon, CheckIcon } from '../../components/icons'
import { releaseExercise, updateExercise } from '../../lib/entries'
import type { Exercise, Question } from '../../types'

const COGNITIVE = ['Remember', 'Understand', 'Apply', 'Analyse', 'Evaluate', 'Create']
const AFFECTIVE = ['Receiving', 'Responding', 'Valuing', 'Organising', 'Characterising']

interface Props {
  entryId: string
  exercise: Exercise
  onChange: (exercise: Exercise) => void
}

/**
 * Screen 3b — the professor reviews the drafted questions, rewords anything the
 * AI got wrong, and only then releases them. Until release the resident cannot
 * see the exercise at all.
 */
export function ExerciseEditor({ entryId, exercise, onChange }: Props) {
  const [questions, setQuestions] = useState<Question[]>(exercise.questions)
  const [saving, setSaving] = useState(false)
  const [releasing, setReleasing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedAt, setSavedAt] = useState<number | null>(null)

  const dirty = useMemo(
    () => JSON.stringify(questions) !== JSON.stringify(exercise.questions),
    [questions, exercise.questions],
  )
  const criticalCount = questions.filter((q) => q.critical).length
  const valid = questions.length > 0 && criticalCount === 1 && questions.every((q) => q.prompt.trim().length >= 10)

  function patch(id: number, part: Partial<Question>) {
    setQuestions((current) => current.map((q) => (q.id === id ? { ...q, ...part } : q)))
  }

  /** Exactly one Critical item, so choosing a new one clears the old. */
  function setCritical(id: number) {
    setQuestions((current) => current.map((q) => ({ ...q, critical: q.id === id })))
  }

  function drop(id: number) {
    setQuestions((current) => current.filter((q) => q.id !== id))
  }

  async function save() {
    if (!valid || saving) return
    setSaving(true)
    setError(null)
    try {
      const updated = await updateExercise(entryId, questions)
      setQuestions(updated.questions)
      onChange(updated)
      setSavedAt(Date.now())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save your changes')
    } finally {
      setSaving(false)
    }
  }

  async function release() {
    if (!valid || releasing) return
    setReleasing(true)
    setError(null)
    try {
      // Never release wording the professor has not committed.
      if (dirty) {
        const updated = await updateExercise(entryId, questions)
        setQuestions(updated.questions)
      }
      onChange(await releaseExercise(entryId))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not release this exercise')
      setReleasing(false)
    }
  }

  return (
    <section className="card exercise">
      <header className="panel-head">
        <div>
          <span className="eyebrow">Screen 3b · review the questions</span>
          <h2 className="panel-title">Edit before your resident sees this</h2>
        </div>
        <span className="pill pill-warm">Draft · not yet released</span>
      </header>

      <p className="certify-lede">
        {exercise.source === 'corti' ? (
          <>
            <AiIcon width={13} height={13} /> Written by AI from the axes you certified.
          </>
        ) : (
          'Generated from the axes you certified.'
        )}{' '}
        Reword anything that is wrong or unclear. The axis each question came from is fixed —
        that is what keeps the cohort comparable.
      </p>

      <ol className="questions">
        {questions.map((question) => (
          <li
            className={`question${question.critical ? ' is-critical' : ''}`}
            key={question.id}
          >
            <div className="question-head">
              <span className="question-num">{question.id}</span>
              <div className="question-tags">
                <span className="pill pill-warm">{question.axis_label}</span>
                <span className="pill">{question.marks} marks</span>
                {question.critical && (
                  <span className="pill pill-alert">
                    <AlertIcon width={11} height={11} />
                    Critical
                  </span>
                )}
              </div>
              {questions.length > 1 && (
                <button
                  type="button"
                  className="question-drop"
                  onClick={() => drop(question.id)}
                  title="Remove this question"
                >
                  Remove
                </button>
              )}
            </div>

            <textarea
              className="question-edit prose"
              value={question.prompt}
              rows={4}
              aria-label={`Question ${question.id} wording`}
              onChange={(event) => patch(question.id, { prompt: event.target.value })}
            />

            <div className="question-meta">
              <label>
                <span>Cognitive</span>
                <select
                  value={question.cognitive}
                  onChange={(event) => patch(question.id, { cognitive: event.target.value })}
                >
                  {COGNITIVE.map((level) => (
                    <option key={level} value={level}>
                      {level}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Affective</span>
                <select
                  value={question.affective}
                  onChange={(event) => patch(question.id, { affective: event.target.value })}
                >
                  {AFFECTIVE.map((level) => (
                    <option key={level} value={level}>
                      {level}
                    </option>
                  ))}
                </select>
              </label>
              <label className="question-marks">
                <span>Marks</span>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={question.marks}
                  onChange={(event) =>
                    patch(question.id, { marks: Number(event.target.value) || 1 })
                  }
                />
              </label>
              <button
                type="button"
                className={`axis-critical${question.critical ? ' is-on' : ''}`}
                onClick={() => setCritical(question.id)}
              >
                <AlertIcon width={13} height={13} />
                {question.critical ? 'Critical question' : 'Make this the critical question'}
              </button>
            </div>
          </li>
        ))}
      </ol>

      <footer className="panel-foot">
        <p className={`panel-status${error ? ' is-error' : ''}`}>
          {error ??
            (criticalCount !== 1
              ? 'Exactly one question must be the critical question'
              : dirty
                ? 'Unsaved changes'
                : savedAt
                  ? 'Changes saved'
                  : 'Releasing hands this to your resident to answer')}
        </p>
        <div className="panel-actions">
          <button
            type="button"
            className="btn btn-quiet"
            disabled={!dirty || !valid || saving}
            onClick={save}
          >
            {saving ? 'Saving…' : 'Save changes'}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!valid || releasing}
            onClick={release}
          >
            <CheckIcon width={16} height={16} />
            {releasing ? 'Releasing…' : 'Release to resident'}
            {!releasing && <ArrowIcon width={16} height={16} />}
          </button>
        </div>
      </footer>
    </section>
  )
}
