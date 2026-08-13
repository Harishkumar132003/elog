import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { AlertIcon, ArrowIcon, CheckIcon } from '../../components/icons'
import { removeQuestion } from '../../lib/cases'
import { getCase, releaseExercise, submitAttempt, updateExercise } from '../../lib/entries'
import type { Attempt, AuthUser, CandidateAxes, Entry, Exercise } from '../../types'
import { QuestionComposer } from './QuestionComposer'
import { ResultPanel } from './ResultPanel'
import './flow.css'
import './exercise-page.css'

/** An answer shorter than this is a decision without its justification, which
 *  §3 scores nothing — so it is not a submission, it is an unfinished one. */
const MIN_ANSWER_CHARS = 40

interface Props {
  entryId: string
  user: AuthUser
  onBack: () => void
  /** The shared case this log belongs to, when the route knows it. */
  onOpenCase?: () => void
}

/** Screen 4 · the whole exercise on one page.
 *
 *  The same page for both roles, which is the point: the professor reads the set
 *  exactly as the resident will meet it before releasing it. Only what is
 *  editable differs — a second, professor-only preview would be one more thing
 *  to keep in sync with this one, and would drift.
 */
export function ExercisePage({ entryId, user, onBack, onOpenCase }: Props) {
  const [entry, setEntry] = useState<Entry | null>(null)
  const [exercise, setExercise] = useState<Exercise | null>(null)
  const [axes, setAxes] = useState<CandidateAxes | null>(null)
  /** The composer is mounted in place rather than on its own page: what to ask
   *  next is decided while looking at what has already been asked. */
  const [composing, setComposing] = useState(false)
  const [attempt, setAttempt] = useState<Attempt | null>(null)
  const [loading, setLoading] = useState(true)

  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [busy, setBusy] = useState(false)
  /** The confirm step. Marking is irreversible, so it gets a deliberate second
   *  gesture rather than firing off the first click. */
  const [confirming, setConfirming] = useState(false)
  /** Which question is mid-flight having the Critical flag moved onto it. */
  const [marking, setMarking] = useState<number | null>(null)
  const [releasing, setReleasing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isProfessor = user.role === 'professor'

  useEffect(() => {
    let live = true
    getCase(entryId)
      .then((snapshot) => {
        if (!live) return
        setEntry(snapshot.entry)
        setAxes(snapshot.axes)
        setExercise(snapshot.exercise)
        setAttempt(snapshot.attempt)
      })
      .catch((cause) =>
        live && setError(cause instanceof Error ? cause.message : 'Could not load this exercise'),
      )
      .finally(() => live && setLoading(false))
    return () => {
      live = false
    }
  }, [entryId])

  // Marking runs in the background, so the page has to come back for the result
  // rather than assume it is there. Only while something is actually pending.
  useEffect(() => {
    if (!attempt?.marking) return
    const timer = setInterval(() => {
      void getCase(entryId)
        .then((snapshot) => snapshot.attempt && setAttempt(snapshot.attempt))
        .catch(() => undefined)
    }, 3000)
    return () => clearInterval(timer)
  }, [attempt?.marking, entryId])

  const questions = useMemo(() => exercise?.questions ?? [], [exercise])
  const totalMarks = questions.reduce((sum, question) => sum + question.marks, 0)
  const answered = questions.filter(
    (question) => (answers[question.id] ?? '').trim().length >= MIN_ANSWER_CHARS,
  ).length
  const ready = questions.length > 0 && answered === questions.length
  const criticalCount = questions.filter((question) => question.critical).length

  // Answering is for the person whose log this is, once released and not yet done.
  const canAnswer = !isProfessor && Boolean(exercise?.released) && !attempt
  // The professor may still prune the set right up until it goes out.
  const canEdit = isProfessor && !exercise?.released && !attempt

  const submit = useCallback(async () => {
    if (!ready || busy) return
    setConfirming(false)
    setBusy(true)
    setError(null)
    try {
      setAttempt(
        await submitAttempt(
          entryId,
          questions.map((question) => ({
            question_id: question.id,
            answer: (answers[question.id] ?? '').trim(),
          })),
        ),
      )
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not submit your answers')
    } finally {
      setBusy(false)
    }
  }, [ready, busy, entryId, questions, answers])

  /** Drop a question. Only before release, and only for the professor — this is
   *  the surface where the set is read whole, so it is where a question that
   *  does not belong gets removed. */
  const drop = useCallback(
    async (questionId: number) => {
      setError(null)
      try {
        setExercise(await removeQuestion(entryId, questionId))
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : 'Could not remove that question')
      }
    },
    [entryId],
  )

  /** Move the Critical flag onto one question, taking it off whichever held it.
   *
   *  Set here rather than only at writing time because which question decides
   *  pass or fail is a judgement about the set as a whole — and this is the
   *  first screen that shows the set as a whole. There is no "unmark": §3.4
   *  gives an exercise exactly one Critical item, so the only move is to put it
   *  somewhere else. The server enforces the same rule and would refuse zero.
   */
  const makeCritical = useCallback(
    async (questionId: number) => {
      if (marking) return
      setMarking(questionId)
      setError(null)
      try {
        setExercise(
          await updateExercise(
            entryId,
            questions.map((question) => ({
              ...question,
              critical: question.id === questionId,
            })),
          ),
        )
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : 'Could not move the critical question')
      } finally {
        setMarking(null)
      }
    },
    [entryId, questions, marking],
  )

  const release = useCallback(async () => {
    if (releasing) return
    setReleasing(true)
    setError(null)
    try {
      setExercise(await releaseExercise(entryId))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not release this exercise')
    } finally {
      setReleasing(false)
    }
  }, [entryId, releasing])

  if (loading) {
    return (
      <div className="case-boot">
        <div className="page-head">
          <div>
            <span className="eyebrow">Reasoning exercise</span>
            <h1 className="page-title">Loading…</h1>
          </div>
        </div>
        <div className="skeleton-card" />
      </div>
    )
  }

  if (!entry || (!exercise && !isProfessor)) {
    return (
      <>
        <div className="page-head">
          <div>
            <span className="eyebrow">Reasoning exercise</span>
            <h1 className="page-title">Nothing to answer yet</h1>
          </div>
        </div>
        <p className="entry-error">
          {error ??
            (isProfessor
              ? 'No questions have been written for this log yet.'
              : 'Your professor has not released an exercise for this log yet.')}
        </p>
        <nav className="xnav">
          <button type="button" className="xnav-back" onClick={onBack}>
            <span aria-hidden>←</span> Back
          </button>

        </nav>
      </>
    )
  }

  return (
    <div className="xpage">
      {/* ── the bar above everything: where you were, and what else to do ── */}
      <nav className="xnav">
        <button type="button" className="xnav-back" onClick={onBack}>
          <span aria-hidden>←</span> Back
        </button>

        <div className="xnav-actions">
          {onOpenCase && (
            <button type="button" className="btn btn-quiet btn-sm" onClick={onOpenCase}>
              The whole case
            </button>
          )}
          {canEdit && !composing && (
            <button
              type="button"
              className="btn btn-quiet btn-sm"
              onClick={() => setComposing(true)}
            >
              + Add question
            </button>
          )}
        </div>
      </nav>

      {/* ── the banner ──────────────────────────────────────────────────
          Answering is a task, not a briefing. Once someone is sitting down to
          write, the banner, the brief and the metadata are all things read
          once and then in the way — so the answering view collapses to a line. */}
      {canAnswer ? (
        <header className="xlean-head">
          <h1>Your reasoning exercise</h1>
          <p>
            {questions.length} question{questions.length === 1 ? '' : 's'} · {totalMarks} marks
            {criticalCount === 1 ? ' · 1 critical' : ''}
          </p>
        </header>
      ) : (
        <header className={`xpage-hero${exercise?.released ? ' is-live' : ''}`}>
          <div className="xpage-hero-text">
            <span className="xpage-eyebrow">
              {entry.role_label} · {entry.subject}
            </span>
            <h1 className="xpage-title">
              {isProfessor ? 'The exercise, as they will meet it' : 'Your reasoning exercise'}
            </h1>
            {entry.competency_title && (
              <p className="xpage-competency">{entry.competency_title}</p>
            )}
          </div>

          <div className="xpage-stats">
            <div className="xpage-stat">
              <strong>{questions.length}</strong>
              <span>question{questions.length === 1 ? '' : 's'}</span>
            </div>
            <div className="xpage-stat">
              <strong>{totalMarks}</strong>
              <span>marks</span>
            </div>
            <div className="xpage-stat is-critical">
              <strong>{criticalCount}</strong>
              <span>critical</span>
            </div>
          </div>
        </header>
      )}

      {/* ── the result, once it exists ─────────────────────────────────── */}
      {attempt?.marking && (
        <section className="card waiting">
          <h2>Marking your answers…</h2>
          <p>
            Your answers are saved. The result appears here as soon as marking finishes — you
            can leave this page and come back.
          </p>
        </section>
      )}
      {/* Summary only: each question below carries its own mark and feedback,
          so the panel's own list would print the whole set a second time. */}
      {attempt && !attempt.marking && <ResultPanel attempt={attempt} breakdown={false} />}

      {/* The log every question was written from. Collapsed, because it is
          reference rather than content — but one click away, because judging a
          question means judging it against what the person actually wrote. */}
      {entry.narrative && !canAnswer && (
        <details className="xsource">
          <summary>
            What the {entry.role_label?.toLowerCase()} logged
            <span className="xsource-hint">the questions are built from this</span>
          </summary>
          <p className="prose">{entry.narrative}</p>
        </details>
      )}

      {/* A set with no Critical item cannot be released, and the reason is not
          obvious from a disabled button alone. */}
      {canEdit && criticalCount !== 1 && (
        <p className="xnote is-warn">
          <AlertIcon width={15} height={15} />
          {criticalCount === 0
            ? 'No critical question yet. Pick the one where a wrong answer is a disqualifying failure — this cannot be released without it.'
            : `${criticalCount} questions are marked critical. An exercise has exactly one; choosing another moves the flag.`}
        </p>
      )}

      {/* ── the questions ──────────────────────────────────────────────── */}
      <ol className="xlist">
        {questions.map((question) => {
          const value = answers[question.id] ?? ''
          const enough = value.trim().length >= MIN_ANSWER_CHARS
          const result = attempt?.results.find((row) => row.question_id === question.id)

          return (
            <li key={question.id} className={`xq${question.critical ? ' is-critical' : ''}`}>
              {/* The number reads as part of the sentence, the way a paper
                  question paper sets it — not as a badge on a rail. */}
              <p className="xq-prompt prose">
                <span className="xq-num">{question.id}.</span>
                {question.prompt}
              </p>

              {canAnswer && (
                <div className="xq-answer">
                  <textarea
                    className="xq-input prose"
                    value={value}
                    rows={5}
                    placeholder="Your decision, and what makes it the right one…"
                    aria-label={`Answer to question ${question.id}`}
                    onChange={(event) =>
                      setAnswers((current) => ({
                        ...current,
                        [question.id]: event.target.value,
                      }))
                    }
                  />
                  {/* Part of the answer box, not metadata: Submit stays disabled
                      until every answer is long enough, and a disabled button
                      with no explanation is the worst of both. */}
                  <p className={`xq-count${enough ? ' is-ok' : ''}`}>
                    {enough ? (
                      <>
                        <CheckIcon width={12} height={12} /> Answered
                      </>
                    ) : (
                      `${Math.max(0, MIN_ANSWER_CHARS - value.trim().length)} more characters`
                    )}
                  </p>
                </div>
              )}

              {/* Once marked, the answer and its mark sit with the question. */}
              {result && (
                <div className={`xresult${result.critical_failed ? ' is-failed' : ''}`}>
                  <div className="xresult-head">
                    <span className={`xverdict is-${result.verdict.replace(/\s+/g, '-')}`}>
                      {result.verdict}
                    </span>
                    <span className="xresult-marks">
                      {result.marks_awarded} / {result.marks} marks
                    </span>
                  </div>
                  {result.answer && <p className="xresult-answer prose">{result.answer}</p>}
                  {result.feedback && <p className="xresult-feedback">{result.feedback}</p>}
                </div>
              )}

              {/* Metadata sits under the question, not over it: it describes
                  what was asked and is read second, if at all. Gone entirely
                  while answering — how a question was built is not something
                  the person answering it needs to see. */}
              {!canAnswer && (
              <div className="xq-foot">
                <span className="xq-tag">
                  Axis: <b>{question.axis_label}</b>
                </span>
                <span className="xq-tag">
                  COG: <b>{question.cognitive}</b>
                </span>
                <span className="xq-tag">
                  AFF: <b>{question.affective}</b>
                </span>
                <span className="xq-tag">
                  PSY: <b>{question.psychomotor}</b>
                </span>
                <span className="xq-tag">
                  Marks: <b>{question.marks}</b>
                </span>
                {question.critical && (
                  <span className="xq-tag is-critical">
                    <AlertIcon width={11} height={11} />
                    Critical question
                  </span>
                )}

                {canEdit && (
                  <div className="xq-foot-actions">
                    {/* Only offered on the questions that are not already it —
                        there is nothing to press on the one that holds it. */}
                    {!question.critical && (
                      <button
                        type="button"
                        className="btn btn-quiet btn-sm"
                        disabled={marking !== null}
                        title="Make this the question that decides pass or fail"
                        onClick={() => void makeCritical(question.id)}
                      >
                        <AlertIcon width={12} height={12} />
                        {marking === question.id ? 'Moving…' : 'Make critical'}
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn btn-quiet btn-sm is-danger"
                      title="Remove this question"
                      onClick={() => void drop(question.id)}
                    >
                      Remove
                    </button>
                  </div>
                )}
              </div>
              )}
            </li>
          )
        })}
      </ol>

      {/* ── writing the next one, in place ─────────────────────────────── */}
      {canEdit && composing && axes && (
        <QuestionComposer
          entryId={entryId}
          axes={axes}
          existing={questions}
          onSaved={setExercise}
          onClose={() => setComposing(false)}
        />
      )}

      {canEdit && !composing && (
        <button type="button" className="xadd" onClick={() => setComposing(true)}>
          + Add {questions.length === 0 ? 'the first question' : 'another question'}
        </button>
      )}

      {error && <p className="entry-error">{error}</p>}

      {/* ── the action bar ─────────────────────────────────────────────── */}
      {canAnswer && (
        <div className="xbar">
          <div className="xbar-progress">
            <div className="xbar-track">
              <div
                className="xbar-fill"
                style={{ width: `${questions.length ? (answered / questions.length) * 100 : 0}%` }}
              />
            </div>
            <span>
              {answered} of {questions.length} answered
            </span>
          </div>
          <button
            type="button"
            className="btn btn-primary btn-lg"
            disabled={!ready || busy}
            onClick={() => setConfirming(true)}
          >
            {busy ? 'Submitting…' : 'Submit for marking'}
            {!busy && <ArrowIcon width={16} height={16} />}
          </button>
        </div>
      )}

      {confirming && (
        <ConfirmSubmit
          questions={questions.length}
          marks={totalMarks}
          criticalId={questions.find((question) => question.critical)?.id ?? null}
          onCancel={() => setConfirming(false)}
          onConfirm={() => void submit()}
        />
      )}

      {/* The professor's own footer: this is the last look before it goes out. */}
      {isProfessor && !exercise?.released && questions.length > 0 && (
        <div className="xbar">
          <p className="xbar-note">
            {criticalCount === 1
              ? 'This is exactly what they will see. Releasing cannot be undone.'
              : `Mark exactly one question as critical before releasing — ${criticalCount} marked.`}
          </p>
          <button
            type="button"
            className="btn btn-primary btn-lg"
            disabled={releasing || criticalCount !== 1 || questions.length === 0}
            onClick={() => void release()}
          >
            {releasing ? 'Releasing…' : `Release to the ${entry.role_label?.toLowerCase()}`}
            {!releasing && <ArrowIcon width={16} height={16} />}
          </button>
        </div>
      )}

      {isProfessor && exercise?.released && !attempt && (
        <div className="xbar is-quiet">
          <p className="xbar-note">
            <CheckIcon width={15} height={15} />
            <span>Released. Waiting for the {entry.role_label?.toLowerCase()} to answer.</span>
          </p>
        </div>
      )}

      {/* No second Back down here — it is in the bar at the top, where a person
          looks for it, and where it does not compete with the primary action. */}
    </div>
  )
}

/** The last gate before marking.
 *
 *  Submitting is one-way: the answers are marked and the result is recorded
 *  against the competency. A single mis-click on a half-finished thought should
 *  not be able to do that, so the primary action is deliberately the second
 *  gesture, and the dialog says plainly what is about to happen.
 */
function ConfirmSubmit({
  questions,
  marks,
  criticalId,
  onCancel,
  onConfirm,
}: {
  questions: number
  marks: number
  criticalId: number | null
  onCancel: () => void
  onConfirm: () => void
}) {
  const confirmRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    confirmRef.current?.focus()
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onCancel()
    document.addEventListener('keydown', onKey)
    // The page behind must not scroll while the dialog owns the screen.
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
    }
  }, [onCancel])

  return (
    <div
      className="xconfirm-scrim"
      role="presentation"
      onClick={(event) => event.target === event.currentTarget && onCancel()}
    >
      <div className="xconfirm" role="dialog" aria-modal="true" aria-labelledby="xconfirm-title">
        <h2 id="xconfirm-title">Submit for marking?</h2>

        <p className="xconfirm-lede">
          All {questions} question{questions === 1 ? '' : 's'} answered, {marks} marks in total.
        </p>

        <ul className="xconfirm-points">
          <li>Your answers are marked and the result is recorded against the competency.</li>
          <li>You cannot change them afterwards, or answer again.</li>
          {criticalId !== null && (
            <li className="is-critical">
              <AlertIcon width={13} height={13} />
              <span>
                Question {criticalId} is the <b>critical</b> one — a wrong answer fails the
                attempt whatever the rest score.
              </span>
            </li>
          )}
        </ul>

        <div className="xconfirm-actions">
          <button type="button" className="btn btn-quiet" onClick={onCancel}>
            Keep editing
          </button>
          <button type="button" className="btn btn-primary" ref={confirmRef} onClick={onConfirm}>
            Submit for marking
            <ArrowIcon width={16} height={16} />
          </button>
        </div>
      </div>
    </div>
  )
}
