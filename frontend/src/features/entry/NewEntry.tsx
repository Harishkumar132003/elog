import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { AiIcon, ArrowIcon, CheckIcon } from '../../components/icons'
import { createEntry, getCompetencies, getSubjects, parseEntryStream } from '../../lib/entries'
import { Dictation, canDictate } from './Dictation'
import type { Analysis, Competency, DopsRole, Entry, Subject, SubjectMeta } from '../../types'
import './entry.css'

const MIN_CHARS = 20
/** Mirrors `max_narrative_chars` on the server. */
const MAX_NARRATIVE = 4000

const PLACEHOLDER: Record<string, string> = {
  clinical:
    'e.g. 55F, fall on outstretched hand. Intra-articular distal radius fracture. Closed reduction attempted, unsatisfactory. Proceeded to ORIF with volar locking plate.',
  'para-clinical':
    'e.g. Core biopsy, breast lump, 45F — reported. Reviewed the slides with the consultant.',
  'pre-clinical': 'e.g. Tutorial on acid-base regulation and compensation.',
}

export function NewEntry({ onSaved }: { onSaved: (entry: Entry) => void }) {
  const [subjects, setSubjects] = useState<SubjectMeta[]>([])
  const [subject, setSubject] = useState<Subject>('Orthopaedics')
  const [narrative, setNarrative] = useState('')
  const [role, setRole] = useState<DopsRole>('supervised')

  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [analysing, setAnalysing] = useState(false)
  /** Seconds the AI has been working; shown once the wait is noticeable. */
  const [waiting, setWaiting] = useState(0)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // The parse is a proposal, not a verdict — the resident can correct it here,
  // and the corrected version is what the reasoning exercise is built from.
  const [editing, setEditing] = useState(false)
  const [fix, setFix] = useState<{
    diagnosis: string
    procedure: string
    age: string
    sex: string
  } | null>(null)

  // The subject's competencies, and the one this case is being logged against.
  // The AI proposes; this is what actually gets saved.
  const [competencies, setCompetencies] = useState<Competency[]>([])
  const [competencyId, setCompetencyId] = useState<string>('')

  // What the current analysis was produced from, so pressing Analyse twice on
  // unchanged text does not spend another AI call.
  const analysedFor = useRef<string | null>(null)
  const textarea = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    getSubjects().then(setSubjects).catch(() => undefined)
  }, [])

  useEffect(() => {
    let live = true
    getCompetencies(subject)
      .then((items) => live && setCompetencies(items))
      .catch(() => live && setCompetencies([]))
    return () => {
      live = false
    }
  }, [subject])

  const meta = useMemo(() => subjects.find((item) => item.value === subject), [subjects, subject])

  useEffect(() => {
    if (!meta) return
    const allowed = meta.roles.map((option) => option.value)
    if (!allowed.includes(role)) setRole(allowed.includes('supervised') ? 'supervised' : allowed[0])
  }, [meta, role])

  useEffect(() => {
    const node = textarea.current
    if (!node) return
    node.style.height = 'auto'
    node.style.height = `${Math.max(170, Math.min(node.scrollHeight, 460))}px`
  }, [narrative])

  const trimmed = narrative.trim()
  const ready = trimmed.length >= MIN_CHARS
  const words = trimmed ? trimmed.split(/\s+/).length : 0
  const key = `${subject}::${trimmed}`
  const reviewing = analysis !== null && analysedFor.current === key

  const analyse = useCallback(async () => {
    if (!ready || analysing) return
    if (analysedFor.current === key && analysis) return // nothing changed
    setAnalysing(true)
    setWaiting(0)
    setError(null)

    // Only the fields the resident has not touched follow the parse. Once they
    // have corrected something, the AI arriving late must not overwrite it.
    const adopt = (result: Analysis, force: boolean) => {
      setAnalysis(result)
      setFix((current) =>
        force || !current
          ? {
              diagnosis: result.parsed.diagnosis?.display ?? '',
              procedure: result.parsed.procedure?.display ?? '',
              age: result.parsed.patient?.age ? String(result.parsed.patient.age) : '',
              sex: result.parsed.patient?.sex ?? '',
            }
          : current,
      )
    }

    try {
      const result = await parseEntryStream(
        subject,
        trimmed,
        {
          // The rule-based read lands in a tenth of a second. Showing it at once
          // beats a spinner: the resident starts checking real values while the
          // AI is still working, and the refined answer replaces them in place.
          onBaseline: (draft) => {
            analysedFor.current = key
            adopt(draft, true)
            setEditing(false)
          },
          onWaiting: setWaiting,
        },
      )
      analysedFor.current = key
      adopt(result, true)
      // The AI's pick seeds the dropdown; with one competency there is nothing to
      // choose and the fallback picks it anyway.
      setCompetencyId(result.competency?.id ?? (competencies.length === 1 ? competencies[0].id : ''))
      setEditing(false)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not read this entry')
    } finally {
      setAnalysing(false)
      setWaiting(0)
    }
  }, [ready, analysing, key, analysis, subject, trimmed, competencies])

  /** Dictation adds to the case, it does not take it over.
   *  The resident may have typed first, and a recording is one more paragraph. */
  const appendDictated = useCallback((text: string) => {
    setNarrative((current) => {
      const joined = current.trim() ? `${current.trimEnd()} ${text}` : text
      // The server caps the narrative too, but stopping here means the resident
      // sees the limit instead of silently losing the end of what they said.
      return joined.length > MAX_NARRATIVE
        ? joined.slice(0, MAX_NARRATIVE).trimEnd()
        : joined
    })
    textarea.current?.focus()
  }, [])

  const patch = useCallback(
    (part: Partial<NonNullable<typeof fix>>) =>
      setFix((current) => (current ? { ...current, ...part } : current)),
    [],
  )

  const save = useCallback(async () => {
    if (!reviewing || saving) return
    if (competencies.length > 1 && !competencyId) return
    setSaving(true)
    setError(null)
    try {
      onSaved(
        await createEntry({
          subject,
          narrative: trimmed,
          role,
          confirmed: true,
          ...(competencyId ? { competency_id: competencyId } : {}),
          ...(fix
            ? {
                diagnosis: fix.diagnosis.trim(),
                procedure: fix.procedure.trim(),
                patient_age: fix.age.trim() ? Number(fix.age) : null,
                patient_sex: fix.sex.trim() || null,
              }
            : {}),
        }),
      )
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save this entry')
      setSaving(false)
    }
  }, [reviewing, saving, subject, trimmed, role, fix, competencyId, competencies.length, onSaved])

  const parsed = analysis?.parsed
  const aiPicked = analysis?.competency != null && analysis.competency.id === competencyId

  /* ── step 2 · review what the system read ──────────────────────────── */
  if (reviewing && analysis) {
    return (
      <div className="entry">
        <header className="entry-head">
          <span className="eyebrow">Step 2 of 2 · check the reading</span>
          <h1 className="entry-title">Is this what you meant?</h1>
          <p className="entry-lede">
            Everything below was read from your entry. Correct anything that is wrong —
            the competency and these fields are what the reasoning exercise is built from.
          </p>
        </header>

        <section className="card review">
          {/* The rules read arrives in a tenth of a second and this screen opens on
              it, so the resident must be told the AI has not finished — otherwise a
              provisional parse looks like a final one. */}
          {analysing && (
            <p className="review-pending">
              <AiIcon width={13} height={13} />
              Still checking with AI{waiting >= 3 ? ` · ${Math.round(waiting)}s` : ''} — these
              fields may still change.
            </p>
          )}

          <div className="review-competency">
            <span className="review-badge">
              <AiIcon width={13} height={13} />
              {aiPicked && analysis.source === 'corti'
                ? 'Competency identified by AI'
                : 'Competency'}
            </span>

            {/* A subject holds dozens of competencies once a curriculum is loaded,
                so the AI's pick is a proposal the resident confirms — the same
                gesture as correcting the diagnosis below. */}
            {competencies.length > 1 ? (
              <>
                <select
                  className="select review-competency-select"
                  value={competencyId}
                  aria-label="Competency this case logs against"
                  onChange={(event) => setCompetencyId(event.target.value)}
                >
                  <option value="">— choose the competency —</option>
                  {competencies.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.title}
                    </option>
                  ))}
                </select>
                <p className="review-competency-hint">
                  {competencyId
                    ? 'The whole reasoning exercise is built on this. Change it if it is wrong.'
                    : 'Pick the competency this case is evidence for.'}
                </p>
              </>
            ) : (
              <h2 className="prose">
                {competencies[0]?.title ?? 'No competency set up for this subject yet'}
              </h2>
            )}
          </div>

          <div className="review-fields-head">
            <span className="eyebrow">Fields read from your entry</span>
            <button
              type="button"
              className="btn btn-quiet"
              onClick={() => setEditing((on) => !on)}
            >
              {editing ? 'Done' : 'Correct these'}
            </button>
          </div>

          {editing && fix ? (
            <div className="review-edit">
              <label className="edit-row">
                <span>Diagnosis</span>
                <input
                  type="text"
                  value={fix.diagnosis}
                  placeholder="not stated"
                  onChange={(event) => patch({ diagnosis: event.target.value })}
                />
              </label>

              <label className="edit-row">
                <span>Procedure</span>
                <input
                  type="text"
                  value={fix.procedure}
                  placeholder="not stated"
                  onChange={(event) => patch({ procedure: event.target.value })}
                />
              </label>

              <div className="edit-row">
                <span>Patient</span>
                <div className="edit-pair">
                  <input
                    type="number"
                    min={0}
                    max={120}
                    value={fix.age}
                    placeholder="age"
                    aria-label="Patient age"
                    onChange={(event) => patch({ age: event.target.value })}
                  />
                  <select
                    value={fix.sex}
                    aria-label="Patient sex"
                    onChange={(event) => patch({ sex: event.target.value })}
                  >
                    <option value="">not stated</option>
                    <option value="Male">Male</option>
                    <option value="Female">Female</option>
                  </select>
                </div>
              </div>

              <p className="edit-note">
                Corrections are saved with the case, and the reasoning exercise is built
                from the corrected version.
              </p>
            </div>
          ) : (
            <dl className="review-fields">
              {(
                [
                  ['Diagnosis', fix?.diagnosis || parsed?.diagnosis?.display],
                  ['Procedure', fix?.procedure || parsed?.procedure?.display],
                  [
                    'Patient',
                    fix && (fix.age || fix.sex)
                      ? [fix.age, fix.sex].filter(Boolean).join(' · ')
                      : parsed?.patient?.display,
                  ],
                  ['Your role', meta?.roles.find((r) => r.value === role)?.label],
                ] as const
              ).map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd className={value ? '' : 'is-blank'}>{value || 'not stated'}</dd>
                </div>
              ))}
            </dl>
          )}

          {parsed && parsed.omissions.length > 0 && (
            <div className="review-gaps">
              <p>
                <strong>You did not document these.</strong> That is not an error — the
                reasoning exercise will ask you about them.
              </p>
              <ul>
                {parsed.omissions.map((omission) => (
                  <li key={omission.id}>{omission.short}</li>
                ))}
              </ul>
            </div>
          )}
        </section>

        {error && <p className="entry-error">{error}</p>}

        <div className="entry-actions">
          <button
            type="button"
            className="btn btn-quiet"
            onClick={() => {
              setAnalysis(null)
              analysedFor.current = null
            }}
          >
            ← Back to edit
          </button>
          <button
            type="button"
            className="btn btn-primary"
            // Without a competency the case has nothing to be evidence *of*, and
            // the whole exercise downstream is built from it.
            disabled={saving || analysing || (competencies.length > 1 && !competencyId)}
            onClick={save}
          >
            <CheckIcon width={16} height={16} />
            {saving ? 'Saving…' : analysing ? 'Waiting for the AI…' : 'Confirm & save to logbook'}
          </button>
        </div>
      </div>
    )
  }

  /* ── step 1 · write the case ───────────────────────────────────────── */
  return (
    <div className="entry">
      <header className="entry-head">
        <span className="eyebrow">Step 1 of 2 · log the case</span>
        <h1 className="entry-title">New logbook entry</h1>
        <p className="entry-lede">
          Write the case as you would in your paper logbook. One case maps to one
          competency, and the reasoning exercise is built from it.
        </p>
      </header>

      <section className="card form">
        <div className="field-block">
          <label className="field-label" htmlFor="subject-tabs">
            Subject
          </label>
          <div className="segmented" id="subject-tabs" role="radiogroup" aria-label="Subject">
            {subjects.map((item) => (
              <button
                key={item.value}
                type="button"
                role="radio"
                aria-checked={item.value === subject}
                className={`segment${item.value === subject ? ' is-on' : ''}`}
                onClick={() => setSubject(item.value)}
              >
                {item.value}
              </button>
            ))}
          </div>
        </div>

        <div className="field-block">
          <label className="field-label" htmlFor="role-group">
            {meta?.subject_class === 'pre-clinical' ? 'Entry type' : 'Your role in this case'}
          </label>
          <div className="segmented" id="role-group" role="radiogroup" aria-label="Your role">
            {(meta?.roles ?? []).map((option) => (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={option.value === role}
                className={`segment segment-role${option.value === role ? ' is-on' : ''}`}
                onClick={() => setRole(option.value)}
              >
                <strong>{option.label}</strong>
                <small>{option.hint}</small>
              </button>
            ))}
          </div>
          <p className="field-help">This decides which variation axes your professor is offered.</p>
        </div>

        <div className="field-block">
          <div className="field-label-row">
            <label className="field-label" htmlFor="narrative">
              {meta?.subject_class === 'pre-clinical'
                ? 'What did you study?'
                : 'What did you do?'}
            </label>
            {canDictate() && <Dictation onText={appendDictated} disabled={analysing} />}
          </div>
          <textarea
            id="narrative"
            ref={textarea}
            className="textbox prose"
            value={narrative}
            placeholder={PLACEHOLDER[meta?.subject_class ?? 'clinical']}
            spellCheck
            onChange={(event) => setNarrative(event.target.value)}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') void analyse()
            }}
          />
          <div className="field-foot">
            <span className="field-help">
              <strong>Free text, not a form.</strong> What you leave out is signal too.
            </span>
            <span className="field-count">
              {words} word{words === 1 ? '' : 's'}
            </span>
          </div>
        </div>
      </section>

      {error && <p className="entry-error">{error}</p>}

      <div className="entry-actions is-single">
        <p className="entry-hint">
          {ready
            ? 'Nothing is saved yet — you will see what the system read first.'
            : `Write at least ${MIN_CHARS} characters to continue.`}
        </p>
        <button
          type="button"
          className="btn btn-primary btn-lg"
          disabled={!ready || analysing}
          onClick={analyse}
        >
          {analysing ? (waiting >= 3 ? `Checking with AI… ${Math.round(waiting)}s` : 'Reading your entry…') : 'Analyse entry'}
          {!analysing && <ArrowIcon width={16} height={16} />}
        </button>
      </div>
    </div>
  )
}
