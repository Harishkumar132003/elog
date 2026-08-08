import { useCallback, useMemo, useState } from 'react'

import { AiIcon, AlertIcon, ArrowIcon } from '../../components/icons'
import { certify, suggestAxes } from '../../lib/entries'
import type { Axis, AxisChoice, AxisSuggestion, CandidateAxes, Exercise } from '../../types'

interface Draft {
  discriminates: boolean
  parameter: string
  marks: number
}

interface Props {
  entryId: string
  axes: CandidateAxes
  onCertified: (exercise: Exercise) => void
}

/** Screen 3 — the professor prunes the closed axis list and sets the fatal error. */
/** Suggested axes arrive pre-ticked, whether freshly generated or served from cache. */
function seedFrom(suggestions: AxisSuggestion[]): Record<string, Draft> {
  return Object.fromEntries(
    suggestions.map((item) => [
      item.axis_id,
      // The parameter stays the professor's to set (§2A) — pre-filling it would
      // be the model deciding rather than proposing.
      { discriminates: true, parameter: '', marks: 10 },
    ]),
  )
}

export function CertifyPanel({ entryId, axes, onCertified }: Props) {
  const [draft, setDraft] = useState<Record<string, Draft>>(() => seedFrom(axes.suggestions))
  const [critical, setCritical] = useState<string | null>(axes.critical_axis)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [suggestions, setSuggestions] = useState<AxisSuggestion[]>(axes.suggestions)
  const [criticalWhy, setCriticalWhy] = useState(axes.critical_why)
  const [suggesting, setSuggesting] = useState(false)
  const [showAll, setShowAll] = useState(axes.suggestions.length === 0)

  const byId = useMemo(() => {
    const map = new Map<string, Axis>()
    for (const family of axes.families) for (const axis of family.axes) map.set(axis.id, axis)
    return map
  }, [axes])

  const suggestedIds = useMemo(
    () => new Set(suggestions.map((s) => s.axis_id)),
    [suggestions],
  )

  const chosen = useMemo(
    () => Object.entries(draft).filter(([, value]) => value.discriminates),
    [draft],
  )
  const ready = chosen.length > 0 && critical !== null && Boolean(draft[critical]?.discriminates)

  const update = useCallback((axisId: string, patch: Partial<Draft>) => {
    setDraft((current) => ({
      ...current,
      [axisId]: {
        discriminates: current[axisId]?.discriminates ?? true,
        parameter: current[axisId]?.parameter ?? '',
        marks: current[axisId]?.marks ?? 10,
        ...patch,
      },
    }))
  }, [])

  function toggle(axisId: string) {
    const wasOn = Boolean(draft[axisId]?.discriminates)
    update(axisId, { discriminates: !wasOn })
    // Un-ticking the fatal-error axis releases the flag.
    if (critical === axisId && wasOn) setCritical(null)
  }

  /** Pull the shortlist and pre-fill it — a proposal the professor prunes. */
  async function askForSuggestions() {
    if (suggesting) return
    setSuggesting(true)
    setError(null)
    try {
      const hint = await suggestAxes(entryId)
      setSuggestions(hint.suggestions)
      setCriticalWhy(hint.critical_why)
      setShowAll(hint.suggestions.length === 0)
      setDraft((current) => ({ ...current, ...seedFrom(hint.suggestions) }))
      if (hint.critical_axis) setCritical(hint.critical_axis)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not suggest axes')
    } finally {
      setSuggesting(false)
    }
  }

  async function submit() {
    if (!ready || busy) return
    setBusy(true)
    setError(null)
    const payload: AxisChoice[] = chosen.map(([axisId, value]) => ({
      axis_id: axisId,
      discriminates: true,
      parameter: value.parameter.trim(),
      critical: axisId === critical,
      marks: value.marks,
    }))
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
    const isCritical = critical === axis.id
    return (
      <li
        key={axis.id}
        className={`axis${on ? ' is-on' : ''}${isCritical ? ' is-critical' : ''}`}
      >
        <label className="axis-main">
          <input
            type="checkbox"
            checked={on}
            onChange={() => toggle(axis.id)}
            aria-label={`${axis.label} discriminates`}
          />
          <span className="axis-text">
            <strong>{axis.label}</strong>
            <small>{suggestion?.reason || axis.varies}</small>
          </span>
          <span className="axis-verdict">{on ? 'discriminates' : 'cosmetic'}</span>
        </label>

        {on && (
          <div className="axis-config">
            <label className="axis-field">
              <span>Parameter</span>
              <input
                type="text"
                value={state?.parameter ?? ''}
                placeholder={axis.example}
                onChange={(event) => update(axis.id, { parameter: event.target.value })}
              />
            </label>
            <label className="axis-field axis-field-narrow">
              <span>Marks</span>
              <input
                type="number"
                min={1}
                max={100}
                value={state?.marks ?? 10}
                onChange={(event) =>
                  update(axis.id, { marks: Number(event.target.value) || 10 })
                }
              />
            </label>
            <button
              type="button"
              className={`axis-critical${isCritical ? ' is-on' : ''}`}
              onClick={() => setCritical(isCritical ? null : axis.id)}
            >
              <AlertIcon width={13} height={13} />
              {isCritical ? 'Fatal error' : 'Mark as fatal'}
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
          {chosen.length} of {totalAxes} ticked
        </span>
      </header>

      <p className="certify-lede">
        These are the only axes the system will offer for this case — filtered by the
        competency and by <strong>{axes.role_label}</strong>. Tick the ones that separate a
        resident who understands from one who does not, and mark the single fatal error.
      </p>

      {suggestions.length === 0 ? (
        <div className="suggest-prompt">
          <button
            type="button"
            className="btn btn-quiet"
            disabled={suggesting}
            onClick={askForSuggestions}
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
            (chosen.length === 0
              ? 'Tick at least one axis that discriminates'
              : critical === null
                ? 'Mark exactly one axis as the fatal error'
                : `${chosen.length} question${chosen.length === 1 ? '' : 's'} will be written from these axes`)}
        </p>
        <button type="button" className="btn btn-primary" disabled={!ready || busy} onClick={submit}>
          {busy ? 'Writing questions…' : 'Certify & generate'}
          {!busy && <ArrowIcon width={16} height={16} />}
        </button>
      </footer>
    </section>
  )
}
