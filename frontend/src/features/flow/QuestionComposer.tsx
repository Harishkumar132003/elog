import { useCallback, useMemo, useState } from 'react'

import { AiIcon, AlertIcon, ArrowIcon, CheckIcon } from '../../components/icons'
import { addQuestion, previewQuestion } from '../../lib/cases'
import { suggestParameters } from '../../lib/entries'
import type { CandidateAxes, Exercise, Question } from '../../types'
import './builder.css'

const DEFAULT_MARKS = 10

// The three closed taxonomies, lowest to highest. Mirrors app/data/bloom.py.
const COGNITIVE = ['Remember', 'Understand', 'Apply', 'Analyse', 'Evaluate', 'Create']
const AFFECTIVE = ['Receiving', 'Responding', 'Valuing', 'Organising', 'Characterising']
const PSYCHOMOTOR = [
  'Perception',
  'Set',
  'Guided response',
  'Mechanism',
  'Complex overt response',
  'Adaptation',
  'Origination',
]

interface Props {
  entryId: string
  axes: CandidateAxes
  /** What is already on this exercise — used only for the position label. */
  existing: Question[]
  onSaved: (exercise: Exercise) => void
  onClose: () => void
}

/** Writing one question: axis → parameter → generate → read it → keep it.
 *
 *  Lives wherever the set is being read rather than on a page of its own. The
 *  professor's judgement about what to ask next is made while looking at what
 *  has already been asked, so separating the two meant navigating away from the
 *  thing the decision depends on.
 *
 *  Generation and saving are separate steps on purpose: the AI writes a draft,
 *  the professor owns the wording, and nothing is stored until they say so.
 */
export function QuestionComposer({ entryId, axes, existing, onSaved, onClose }: Props) {
  const [axisId, setAxisId] = useState('')
  const [parameter, setParameter] = useState('')
  const [marks, setMarks] = useState(DEFAULT_MARKS)
  const [critical, setCritical] = useState(false)

  /** Generated, not yet stored. While this is set the card is in "read it
   *  before you keep it" mode. */
  const [draft, setDraft] = useState<Question | null>(null)

  const [generating, setGenerating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [suggesting, setSuggesting] = useState(false)
  /** Suggestions fetched but not used yet — pressing ✦ again costs no round
   *  trip until the set is spent. */
  const [pool, setPool] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  /** Every axis this role may be asked about, flattened out of its families. */
  const offered = useMemo(() => axes.families.flatMap((family) => family.axes), [axes])
  const byId = useMemo(() => new Map(offered.map((axis) => [axis.id, axis])), [offered])
  const suggested = useMemo(
    () => new Set(axes.suggestions.map((item) => item.axis_id)),
    [axes],
  )
  const axis = byId.get(axisId)
  const criticalCount = existing.filter((question) => question.critical).length

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
      // certification, so the only thing worth sending is whatever is sitting
      // unsaved in the box.
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
      onSaved(
        await addQuestion(entryId, {
          axis_id: draft.axis_id,
          parameter: parameter.trim(),
          marks: draft.marks,
          critical: draft.critical,
          prompt: draft.prompt.trim(),
          cognitive: draft.cognitive,
          affective: draft.affective,
          psychomotor: draft.psychomotor,
        }),
      )
      // Clear for the next one, but keep the axis: a professor often wants two
      // variations of the same kind before moving on.
      setDraft(null)
      setParameter('')
      setCritical(false)
      setMarks(DEFAULT_MARKS)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save that question')
    } finally {
      setSaving(false)
    }
  }, [draft, saving, entryId, parameter, onSaved])

  return (
    <section className="card builder-card">
      <header className="builder-card-head">
        <span className="builder-number">Question {existing.length + 1}</span>
        <div className="builder-head-actions">
          {axes.suggestions.length > 0 && !axisId && (
            <span className="builder-nudge">
              <AiIcon width={13} height={13} />
              The AI shortlisted {axes.suggestions.length} axes for this case
            </span>
          )}
          <button type="button" className="btn btn-quiet btn-sm" onClick={onClose}>
            Done adding
          </button>
        </div>
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
        {axis && (
          <p className="builder-hint">
            {axis.varies}. For example: {axis.example}
          </p>
        )}
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
            {existing.filter((q) => q.critical).map((q) => q.id).join(', ')} — an exercise
            has exactly one.
          </span>
        </p>
      )}

      {error && <p className="entry-error">{error}</p>}

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
            {(
              [
                ['Cognitive', 'cognitive', COGNITIVE],
                ['Affective', 'affective', AFFECTIVE],
                ['Psychomotor', 'psychomotor', PSYCHOMOTOR],
              ] as const
            ).map(([label, field, levels]) => (
              <label className="builder-draft-field" key={field}>
                <span className="field-label">{label}</span>
                <select
                  className="select"
                  value={draft[field]}
                  onChange={(event) => editDraft({ [field]: event.target.value })}
                >
                  {levels.map((level) => (
                    <option key={level} value={level}>
                      {level}
                    </option>
                  ))}
                </select>
              </label>
            ))}

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
              {saving ? 'Saving…' : `Save as question ${existing.length + 1}`}
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
