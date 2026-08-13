import { useCallback, useEffect, useMemo, useState } from 'react'

import { AiIcon, AlertIcon, ArrowIcon, CheckIcon } from '../../components/icons'
import { addQuestion, previewQuestion } from '../../lib/cases'
import { getCase, suggestParameters } from '../../lib/entries'
import type { CandidateAxes, Entry, Exercise, Question } from '../../types'
import './flow.css'
import './builder.css'

const DEFAULT_MARKS = 10

// The two closed Bloom lists, same as the exercise editor offers.
const COGNITIVE = ['Remember', 'Understand', 'Apply', 'Analyse', 'Evaluate', 'Create']
const AFFECTIVE = ['Receiving', 'Responding', 'Valuing', 'Organising', 'Characterising']

interface Props {
  entryId: string
  onDone: () => void
  /** Open the exercise page — the set as the participant will meet it. */
  onPreview: () => void
}

/** Screen 3 · build one participant's question set, a card at a time.
 *
 *  Choose an axis, settle on a parameter, generate, **read and edit it**, keep
 *  it, move on. Generation and saving are separate steps: the AI writes a
 *  draft, the professor owns the wording, and nothing is stored until they say
 *  so. A question they could not read before committing is one they would have
 *  to delete afterwards.
 */
export function QuestionBuilder({ entryId, onDone, onPreview }: Props) {
  const [entry, setEntry] = useState<Entry | null>(null)
  const [axes, setAxes] = useState<CandidateAxes | null>(null)
  const [exercise, setExercise] = useState<Exercise | null>(null)
  const [loading, setLoading] = useState(true)

  // The card being written now.
  const [axisId, setAxisId] = useState('')
  const [parameter, setParameter] = useState('')
  const [marks, setMarks] = useState(DEFAULT_MARKS)
  const [critical, setCritical] = useState(false)

  /** The generated question, held here and not yet stored. While this is set the
   *  screen is in "read it before you keep it" mode. */
  const [draft, setDraft] = useState<Question | null>(null)

  const [generating, setGenerating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [suggesting, setSuggesting] = useState(false)
  /** Suggestions fetched but not used yet. Corti returns up to three at a time,
   *  so pressing ✦ again costs no round trip until the set is spent. */
  const [pool, setPool] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    getCase(entryId)
      .then((snapshot) => {
        if (!live) return
        setEntry(snapshot.entry)
        setAxes(snapshot.axes)
        setExercise(snapshot.exercise)
      })
      .catch((cause) =>
        live && setError(cause instanceof Error ? cause.message : 'Could not load this log'),
      )
      .finally(() => live && setLoading(false))
    return () => {
      live = false
    }
  }, [entryId])

  /** Every axis this role may be asked about, flattened out of its families. */
  const offered = useMemo(
    () => (axes?.families ?? []).flatMap((family) => family.axes),
    [axes],
  )

  const byId = useMemo(() => new Map(offered.map((axis) => [axis.id, axis])), [offered])

  const suggested = useMemo(
    () => new Set((axes?.suggestions ?? []).map((item) => item.axis_id)),
    [axes],
  )

  const questions = exercise?.questions ?? []
  const released = Boolean(exercise?.released)
  const criticalCount = questions.filter((question) => question.critical).length
  const axis = byId.get(axisId)

  // A new axis is a new line of questioning; carrying the old suggestions over
  // would offer variations of something no longer being asked.
  const chooseAxis = useCallback((next: string) => {
    setAxisId(next)
    setParameter('')
    setPool([])
    setDraft(null)
    setError(null)
  }, [])

  const suggest = useCallback(async () => {
    if (!axisId || suggesting) return

    // Spend the pool first — a second press should give a different variation,
    // not another round trip for the same three.
    if (pool.length) {
      setParameter(pool[0])
      setPool((rest) => rest.slice(1))
      return
    }

    setSuggesting(true)
    setError(null)
    try {
      // The server reads what this log already has on this axis from its own
      // certification — a generated question does not carry the parameter
      // behind it, so the client has nothing useful to contribute here except
      // whatever is sitting unsaved in the box.
      const result = await suggestParameters(
        entryId,
        axisId,
        parameter.trim() ? [parameter.trim()] : [],
      )
      if (!result.parameters.length) {
        setError('No parameters came back for that axis — write your own.')
      } else {
        setParameter(result.parameters[0])
        setPool(result.parameters.slice(1))
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The AI could not be reached')
    } finally {
      setSuggesting(false)
    }
  }, [axisId, suggesting, pool, parameter, entryId])

  /** Write a question and show it. Nothing is stored yet. */
  const generate = useCallback(async () => {
    if (!axisId || !parameter.trim() || generating) return
    setGenerating(true)
    setError(null)
    try {
      setDraft(
        await previewQuestion(entryId, {
          axis_id: axisId,
          parameter: parameter.trim(),
          marks,
          critical,
        }),
      )
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not write that question')
    } finally {
      setGenerating(false)
    }
  }, [axisId, parameter, generating, entryId, marks, critical])

  const editDraft = useCallback(
    (part: Partial<Question>) =>
      setDraft((current) => (current ? { ...current, ...part } : current)),
    [],
  )

  /** Commit the draft as the professor left it. The wording goes with the
   *  request, so nothing is regenerated and no second AI call is spent. */
  const keep = useCallback(async () => {
    if (!draft || saving || draft.prompt.trim().length < 10) return
    setSaving(true)
    setError(null)
    try {
      const updated = await addQuestion(entryId, {
        axis_id: draft.axis_id,
        parameter: parameter.trim(),
        marks: draft.marks,
        critical: draft.critical,
        prompt: draft.prompt.trim(),
        cognitive: draft.cognitive,
        affective: draft.affective,
      })
      setExercise(updated)
      setDraft(null)
      // Clear the card for the next question, but keep the axis: a professor
      // often wants two variations of the same kind before moving on.
      setParameter('')
      setCritical(false)
      setMarks(DEFAULT_MARKS)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save that question')
    } finally {
      setSaving(false)
    }
  }, [draft, saving, entryId, parameter])

  // Releasing lives on the exercise page now — reading the set whole is the
  // gesture that should precede handing it over.

  if (loading) {
    return (
      <div className="case-boot">
        <div className="page-head">
          <div>
            <span className="eyebrow">Questions</span>
            <h1 className="page-title">Loading…</h1>
          </div>
        </div>
        <div className="skeleton-card" />
      </div>
    )
  }

  if (!entry || !axes) {
    return (
      <>
        <div className="page-head">
          <div>
            <span className="eyebrow">Questions</span>
            <h1 className="page-title">Not available</h1>
          </div>
        </div>
        <p className="entry-error">{error ?? 'This log does not exist, or is not yours to mark.'}</p>
      </>
    )
  }

  return (
    <div className="builder">
      <header className="page-head">
        <div>
          <span className="eyebrow">
            {entry.role_label} · {entry.subject}
          </span>
          <h1 className="page-title">Build the reasoning questions</h1>
          <p className="builder-lede">
            One question at a time. Pick the kind of variation, settle on what it actually is
            for this case, and the AI writes the question — you keep it or discard it.
          </p>
        </div>

        {/* The set itself is read on the exercise page. All this needs to carry
            is how far along it is and the way through to it. */}
        <div className="builder-head-actions">
          <button type="button" className="btn btn-quiet" onClick={onDone}>
            ← Back to case
          </button>
          {questions.length > 0 && (
            <button type="button" className="btn btn-primary" onClick={onPreview}>
              {released
                ? `View the ${questions.length} released`
                : `Review ${questions.length} & release`}
              <ArrowIcon width={15} height={15} />
            </button>
          )}
        </div>
      </header>

      {/* ── what this person wrote ────────────────────────────────────── */}
      <section className="card builder-source">
        <span className="eyebrow">What the {entry.role_label?.toLowerCase()} logged</span>
        <p className="prose">{entry.narrative}</p>
        {entry.competency_title && (
          <p className="builder-competency">{entry.competency_title}</p>
        )}
      </section>

      {/* ── the card being written ────────────────────────────────────── */}
      {released ? (
        <section className="card builder-released">
          <CheckIcon width={18} height={18} />
          <div>
            <strong>Released to the {entry.role_label?.toLowerCase()}</strong>
            <p>
              They can see and answer these {questions.length} question
              {questions.length === 1 ? '' : 's'} now. A released exercise can no longer be
              changed.
            </p>
          </div>
        </section>
      ) : (
        <section className="card builder-card">
          <header className="builder-card-head">
            <span className="builder-number">Question {questions.length + 1}</span>
            {axes.suggestions.length > 0 && !axisId && (
              <span className="builder-nudge">
                <AiIcon width={13} height={13} />
                The AI shortlisted {axes.suggestions.length} axes for this case
              </span>
            )}
          </header>

          <label className="builder-field">
            <span className="field-label">What kind of variation?</span>
            <select
              className="select"
              value={axisId}
              onChange={(event) => chooseAxis(event.target.value)}
            >
              <option value="">— choose an axis —</option>
              {/* A flat list, not grouped by family. The family names are the
                  spec's own vocabulary and mean nothing to the professor at the
                  moment of choosing — the axis label already says what varies. */}
              {offered.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                  {suggested.has(option.id) ? '  ✦ suggested' : ''}
                </option>
              ))}
            </select>
            {axis && <p className="builder-hint">{axis.varies}. For example: {axis.example}</p>}
          </label>

          <label className="builder-field">
            <span className="field-label">What is the variation, for this case?</span>
            <div className="builder-param">
              <input
                type="text"
                className="builder-input"
                value={parameter}
                disabled={!axisId}
                placeholder={axis ? axis.example : 'Choose an axis first'}
                onChange={(event) => setParameter(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') void generate()
                }}
              />
              <button
                type="button"
                className="param-suggest"
                title="Suggest a parameter for this axis"
                disabled={!axisId || suggesting}
                onClick={() => void suggest()}
              >
                {suggesting ? '…' : <AiIcon width={14} height={14} />}
              </button>
            </div>
            <p className="builder-hint">
              The change itself, not the question — “presenting on day 5 with a walled-off mass”,
              not “what would you do if…”.
              {pool.length > 0 && ` ${pool.length} more suggestion${pool.length === 1 ? '' : 's'} ready.`}
            </p>
          </label>

          <div className="builder-row">
            <label className="builder-marks">
              <span className="field-label">Marks</span>
              <input
                type="number"
                min={1}
                max={100}
                value={marks}
                onChange={(event) => setMarks(Number(event.target.value) || DEFAULT_MARKS)}
              />
            </label>

            <button
              type="button"
              role="checkbox"
              aria-checked={critical}
              className={`builder-critical${critical ? ' is-on' : ''}`}
              onClick={() => setCritical((on) => !on)}
            >
              <AlertIcon width={14} height={14} />
              {critical ? 'Critical question' : 'Make this the critical question'}
            </button>

            <button
              type="button"
              className="btn btn-primary builder-generate"
              disabled={!axisId || !parameter.trim() || generating}
              onClick={() => void generate()}
            >
              {generating
                ? 'Writing the question…'
                : draft
                  ? 'Write another version'
                  : 'Generate question'}
              {!generating && <ArrowIcon width={16} height={16} />}
            </button>
          </div>

          {critical && criticalCount > 0 && !draft && (
            <p className="builder-note">
              <span>
                This will take the critical flag off question{' '}
                {questions.filter((q) => q.critical).map((q) => q.id).join(', ')} — an exercise
                has exactly one.
              </span>
            </p>
          )}

          {/* ── read it, change it, then keep it ─────────────────────────── */}
          {draft && (
            <div className="builder-draft">
              <header className="builder-draft-head">
                <span className="eyebrow">Nothing is saved yet — edit anything below</span>
                <span className="builder-draft-axis">{draft.axis_label}</span>
              </header>

              <textarea
                className="builder-draft-text prose"
                value={draft.prompt}
                rows={4}
                aria-label="The question, as it will be asked"
                onChange={(event) => editDraft({ prompt: event.target.value })}
              />
              {draft.prompt.trim().length < 10 && (
                <p className="builder-hint is-warn">A question needs at least 10 characters.</p>
              )}

              <div className="builder-draft-row">
                <label className="builder-draft-field">
                  <span className="field-label">Cognitive</span>
                  <select
                    className="select"
                    value={draft.cognitive}
                    onChange={(event) => editDraft({ cognitive: event.target.value })}
                  >
                    {COGNITIVE.map((level) => (
                      <option key={level} value={level}>
                        {level}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="builder-draft-field">
                  <span className="field-label">Affective</span>
                  <select
                    className="select"
                    value={draft.affective}
                    onChange={(event) => editDraft({ affective: event.target.value })}
                  >
                    {AFFECTIVE.map((level) => (
                      <option key={level} value={level}>
                        {level}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="builder-marks">
                  <span className="field-label">Marks</span>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={draft.marks}
                    onChange={(event) =>
                      editDraft({ marks: Number(event.target.value) || DEFAULT_MARKS })
                    }
                  />
                </label>

                <button
                  type="button"
                  role="checkbox"
                  aria-checked={draft.critical}
                  className={`builder-critical${draft.critical ? ' is-on' : ''}`}
                  onClick={() => editDraft({ critical: !draft.critical })}
                >
                  <AlertIcon width={14} height={14} />
                  {draft.critical ? 'Critical question' : 'Make this the critical question'}
                </button>
              </div>

              {draft.critical && criticalCount > 0 && (
                <p className="builder-note">
                  <span>
                    Saving this takes the critical flag off question{' '}
                    {questions.filter((q) => q.critical).map((q) => q.id).join(', ')} — an
                    exercise has exactly one.
                  </span>
                </p>
              )}

              <div className="builder-draft-actions">
                <button
                  type="button"
                  className="btn btn-quiet"
                  disabled={saving}
                  onClick={() => setDraft(null)}
                >
                  Discard
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={saving || draft.prompt.trim().length < 10}
                  onClick={() => void keep()}
                >
                  <CheckIcon width={16} height={16} />
                  {saving ? 'Saving…' : `Save as question ${questions.length + 1}`}
                </button>
              </div>
            </div>
          )}
        </section>
      )}

      {error && <p className="entry-error">{error}</p>}

    </div>
  )
}
