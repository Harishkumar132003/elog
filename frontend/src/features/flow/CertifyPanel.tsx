import { useCallback, useMemo, useState } from 'react'

import { AiIcon, AlertIcon, ArrowIcon } from '../../components/icons'
import { certify, suggestAxes, suggestParameters } from '../../lib/entries'
import type { Axis, AxisChoice, AxisSuggestion, CandidateAxes, Exercise } from '../../types'

interface Parameter {
  text: string
  marks: number
  critical: boolean
}

interface Draft {
  discriminates: boolean
  parameters: Parameter[]
}

interface Props {
  entryId: string
  axes: CandidateAxes
  onCertified: (exercise: Exercise) => void
}

const blank = (): Parameter => ({ text: '', marks: 10, critical: false })

/** Suggested axes arrive pre-ticked, whether freshly generated or served from cache. */
function seedFrom(suggestions: AxisSuggestion[]): Record<string, Draft> {
  return Object.fromEntries(
    suggestions.map((item) => [item.axis_id, { discriminates: true, parameters: [blank()] }]),
  )
}

/** Screen 3 — the professor prunes the closed axis list and sets the critical question. */
export function CertifyPanel({ entryId, axes, onCertified }: Props) {
  const [draft, setDraft] = useState<Record<string, Draft>>(() => seedFrom(axes.suggestions))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [suggestions, setSuggestions] = useState<AxisSuggestion[]>(axes.suggestions)
  const [criticalWhy, setCriticalWhy] = useState(axes.critical_why)
  const [suggesting, setSuggesting] = useState(false)
  /** Which row is currently asking the AI, as `axisId:index`. */
  const [thinking, setThinking] = useState<string | null>(null)
  /** Suggestions fetched but not yet used, per axis. Corti returns up to three
   *  at a time, so filling the second row costs no round trip and cannot repeat
   *  what the first one already took. */
  const [pool, setPool] = useState<Record<string, string[]>>({})
  const [showAll, setShowAll] = useState(axes.suggestions.length === 0)

  const byId = useMemo(() => {
    const map = new Map<string, Axis>()
    for (const family of axes.families) for (const axis of family.axes) map.set(axis.id, axis)
    return map
  }, [axes])

  const suggestedIds = useMemo(() => new Set(suggestions.map((s) => s.axis_id)), [suggestions])

  /** Every parameter that will actually become a question. A row left blank is an
   *  unfilled row, not a question with no variation, so it does not count. */
  const slots = useMemo(
    () =>
      Object.entries(draft)
        .filter(([, value]) => value.discriminates)
        .flatMap(([axisId, value]) =>
          value.parameters
            .map((parameter, index) => ({ axisId, index, ...parameter }))
            .filter((parameter) => parameter.text.trim()),
        ),
    [draft],
  )
  const criticalCount = slots.filter((slot) => slot.critical).length
  const ready = slots.length > 0 && criticalCount === 1

  const edit = useCallback(
    (axisId: string, change: (current: Draft) => Draft) =>
      setDraft((all) => ({
        ...all,
        [axisId]: change(all[axisId] ?? { discriminates: true, parameters: [blank()] }),
      })),
    [],
  )

  function toggle(axisId: string) {
    const current = draft[axisId]
    const on = Boolean(current?.discriminates)
    edit(axisId, (state) => ({
      discriminates: !on,
      // Ticking an axis for the first time opens one empty row to type into.
      parameters: state.parameters.length ? state.parameters : [blank()],
    }))
  }

  const patch = useCallback(
    (axisId: string, index: number, part: Partial<Parameter>) =>
      edit(axisId, (state) => ({
        ...state,
        parameters: state.parameters.map((p, i) => (i === index ? { ...p, ...part } : p)),
      })),
    [edit],
  )

  const addParameter = useCallback(
    (axisId: string) =>
      edit(axisId, (state) => ({ ...state, parameters: [...state.parameters, blank()] })),
    [edit],
  )

  const dropParameter = useCallback(
    (axisId: string, index: number) =>
      edit(axisId, (state) => {
        const parameters = state.parameters.filter((_, i) => i !== index)
        return { ...state, parameters: parameters.length ? parameters : [blank()] }
      }),
    [edit],
  )

  /** Exactly one critical question in the whole exercise, so choosing a new one
   *  clears the old — wherever in the list it happened to be. */
  function setCritical(axisId: string, index: number, on: boolean) {
    setDraft((all) =>
      Object.fromEntries(
        Object.entries(all).map(([id, state]) => [
          id,
          {
            ...state,
            parameters: state.parameters.map((p, i) => ({
              ...p,
              critical: on && id === axisId && i === index,
            })),
          },
        ]),
      ),
    )
  }

  /** Pull the shortlist and pre-tick it — a proposal the professor prunes. */
  async function askForAxes() {
    if (suggesting) return
    setSuggesting(true)
    setError(null)
    try {
      const hint = await suggestAxes(entryId)
      setSuggestions(hint.suggestions)
      setCriticalWhy(hint.critical_why)
      setShowAll(hint.suggestions.length === 0)
      setDraft((current) => ({ ...seedFrom(hint.suggestions), ...current }))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not suggest axes')
    } finally {
      setSuggesting(false)
    }
  }

  /** Fill ONE row with a concrete way to vary this case along its axis.
   *
   *  Per row rather than per axis: the professor decides how many parameters
   *  they want, and asking fills the box they pressed. Corti hands back up to
   *  three, so the rest are kept for the next row — instant, and it cannot
   *  propose something already sitting in another row of the same axis.
   */
  async function askForParameter(axisId: string, index: number) {
    if (thinking) return
    const taken = new Set(
      (draft[axisId]?.parameters ?? [])
        .map((p) => p.text.trim().toLowerCase())
        .filter(Boolean),
    )

    const ready = (pool[axisId] ?? []).filter((text) => !taken.has(text.toLowerCase()))
    if (ready.length) {
      patch(axisId, index, { text: ready[0] })
      setPool((all) => ({ ...all, [axisId]: ready.slice(1) }))
      return
    }

    setThinking(`${axisId}:${index}`)
    setError(null)
    try {
      const { parameters } = await suggestParameters(entryId, axisId, [...taken])
      const fresh = parameters.filter((text) => !taken.has(text.trim().toLowerCase()))
      if (!fresh.length) {
        setError(
          parameters.length
            ? 'Nothing new came back for that axis — write your own'
            : 'No parameters came back for that axis — write your own',
        )
        return
      }
      patch(axisId, index, { text: fresh[0] })
      setPool((all) => ({ ...all, [axisId]: fresh.slice(1) }))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not suggest a parameter')
    } finally {
      setThinking(null)
    }
  }

  async function submit() {
    if (!ready || busy) return
    setBusy(true)
    setError(null)
    const payload: AxisChoice[] = Object.entries(draft)
      .filter(([, value]) => value.discriminates)
      .map(([axisId, value]) => ({
        axis_id: axisId,
        discriminates: true,
        parameters: value.parameters
          .filter((p) => p.text.trim())
          .map((p) => ({ text: p.text.trim(), marks: p.marks, critical: p.critical })),
      }))
      .filter((axis) => axis.parameters.length > 0)
    try {
      onCertified(await certify(entryId, payload))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not certify this case')
      setBusy(false)
    }
  }

  const totalAxes = axes.families.reduce((n, f) => n + f.axes.length, 0)

  function renderAxis(axis: Axis, suggestion?: AxisSuggestion) {
    const state = draft[axis.id]
    const on = Boolean(state?.discriminates)
    const parameters = state?.parameters ?? []
    const hasCritical = parameters.some((p) => p.critical)

    return (
      <li key={axis.id} className={`axis${on ? ' is-on' : ''}${hasCritical ? ' is-critical' : ''}`}>
        <label className="axis-main">
          <input
            type="checkbox"
            checked={on}
            onChange={() => toggle(axis.id)}
            aria-label={`Test ${axis.label}`}
          />
          <span className="axis-text">
            <strong>{axis.label}</strong>
            <small>{suggestion?.reason || axis.varies}</small>
          </span>
        </label>

        {on && (
          <div className="axis-params">
            <div className="axis-params-head">
              <span className="eyebrow">
                {parameters.length === 1 ? 'Parameter' : `${parameters.length} parameters`} · one
                question each
              </span>
            </div>

            {parameters.map((parameter, index) => (
              <div className="param" key={index}>
                <span className="param-input">
                  <input
                    type="text"
                    className="param-text"
                    value={parameter.text}
                    placeholder={axis.example}
                    aria-label={`${axis.label} parameter ${index + 1}`}
                    onChange={(event) => patch(axis.id, index, { text: event.target.value })}
                  />
                  {/* Fills this box only. The professor decides how many
                      parameters there are; this just saves the typing. */}
                  <button
                    type="button"
                    className="param-suggest"
                    disabled={thinking !== null}
                    title="Suggest a variation for this box"
                    aria-label={`Suggest a parameter for ${axis.label}, row ${index + 1}`}
                    onClick={() => askForParameter(axis.id, index)}
                  >
                    {thinking === `${axis.id}:${index}` ? (
                      <span className="param-spin" aria-hidden />
                    ) : (
                      <AiIcon width={14} height={14} />
                    )}
                  </button>
                </span>
                <input
                  type="number"
                  className="param-marks"
                  min={1}
                  max={100}
                  value={parameter.marks}
                  aria-label="Marks"
                  onChange={(event) =>
                    patch(axis.id, index, { marks: Number(event.target.value) || 10 })
                  }
                />
                <button
                  type="button"
                  className={`axis-critical${parameter.critical ? ' is-on' : ''}`}
                  title="The one question whose wrong answer fails the whole exercise"
                  onClick={() => setCritical(axis.id, index, !parameter.critical)}
                >
                  <AlertIcon width={13} height={13} />
                  {parameter.critical ? 'Critical question' : 'Make this the critical question'}
                </button>
                {parameters.length > 1 && (
                  <button
                    type="button"
                    className="param-drop"
                    aria-label={`Remove parameter ${index + 1}`}
                    onClick={() => dropParameter(axis.id, index)}
                  >
                    Remove
                  </button>
                )}
              </div>
            ))}

            <button
              type="button"
              className="btn btn-ghost param-add"
              onClick={() => addParameter(axis.id)}
            >
              + Add parameter
            </button>
          </div>
        )}
      </li>
    )
  }

  return (
    <section className="card certify">
      <header className="panel-head">
        <div>
          <span className="eyebrow">Screen 3 · certify</span>
          <h2 className="panel-title">Which variations actually discriminate?</h2>
        </div>
        <span className="pill">
          {slots.length} question{slots.length === 1 ? '' : 's'}
        </span>
      </header>

      <p className="certify-lede">
        These are the only axes the system will offer for this case — filtered by the
        competency and by <strong>{axes.role_label}</strong>. Tick the ones that separate a
        resident who understands from one who does not, give each a parameter, and mark the
        one question that must be answered correctly.
      </p>

      {suggestions.length === 0 ? (
        <div className="suggest-prompt">
          <button
            type="button"
            className="btn btn-quiet"
            disabled={suggesting}
            onClick={askForAxes}
          >
            <AiIcon width={14} height={14} />
            {suggesting ? 'Reading the case…' : 'Suggest which axes matter'}
          </button>
          <span>Narrows {totalAxes} axes to the few worth testing. You decide.</span>
        </div>
      ) : (
        <div className="suggested">
          <div className="suggested-head">
            <span className="eyebrow">
              <AiIcon width={12} height={12} /> Suggested for this case
            </span>
            <span className="suggested-note">Pre-ticked — untick anything you disagree with</span>
          </div>
          <ul className="axis-list">
            {suggestions.map((item) => {
              const axis = byId.get(item.axis_id)
              return axis ? renderAxis(axis, item) : null
            })}
          </ul>
          {criticalWhy && (
            <p className="suggested-critical">
              <AlertIcon width={13} height={13} />
              {criticalWhy}
            </p>
          )}
        </div>
      )}

      {suggestions.length > 0 && !showAll && (
        <div className="suggest-more">
          <button type="button" className="btn btn-ghost" onClick={() => setShowAll(true)}>
            Show all {totalAxes} offered axes
          </button>
        </div>
      )}

      {showAll && (
        <div className="families">
          {axes.families.map((family) => {
            const rest = family.axes.filter((axis) => !suggestedIds.has(axis.id))
            if (rest.length === 0) return null
            return (
              <div className="family" key={family.id}>
                <div className="family-head">
                  <h3>{family.label}</h3>
                  <p>{family.description}</p>
                </div>
                <ul className="axis-list">{rest.map((axis) => renderAxis(axis))}</ul>
              </div>
            )
          })}
        </div>
      )}

      <footer className="panel-foot">
        <p className={`panel-status${error ? ' is-error' : ''}`}>
          {error ??
            (slots.length === 0
              ? 'Tick an axis and give it at least one parameter'
              : criticalCount === 0
                ? 'Mark one parameter as the critical question'
                : criticalCount > 1
                  ? `Only one parameter can be the critical question — ${criticalCount} are marked`
                  : `${slots.length} question${slots.length === 1 ? '' : 's'} will be written`)}
        </p>
        <button type="button" className="btn btn-primary" disabled={!ready || busy} onClick={submit}>
          {busy ? 'Writing questions…' : 'Certify & generate'}
          {!busy && <ArrowIcon width={16} height={16} />}
        </button>
      </footer>
    </section>
  )
}
