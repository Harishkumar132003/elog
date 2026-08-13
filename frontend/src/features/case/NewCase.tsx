import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { AiIcon, ArrowIcon, CheckIcon } from '../../components/icons'
import { Dictation, canDictate } from '../entry/Dictation'
import { TranscribeLoader } from '../entry/TranscribeLoader'
import { createCase, listRoles } from '../../lib/cases'
import { getCompetencies, getSubjects, parseEntryStream } from '../../lib/entries'
import { useAuth } from '../../lib/auth'
import type { Analysis, Case, Competency, DopsRole, Subject, SubjectMeta } from '../../types'
import '../entry/entry.css'
import './case.css'

const MIN_CHARS = 20
/** Mirrors `max_narrative_chars` on the server. */
const MAX_NARRATIVE = 4000

const PLACEHOLDER: Record<string, string> = {
  clinical:
    'e.g. 55F, fall on outstretched hand. Intra-articular distal radius fracture. Closed reduction attempted, unsatisfactory. Proceeded to ORIF with volar locking plate.',
  'para-clinical':
    'e.g. Core biopsy, breast lump, 45F — reported with the consultant.',
  'pre-clinical': 'e.g. Tutorial on acid-base regulation and compensation.',
}

interface RoleOption {
  key: string
  name: string
  dops_role: DopsRole
}

/** Screen 1 · the case everyone in the room shares.
 *
 *  This is deliberately NOT anyone's log. It is the clinical facts — what
 *  happened, to whom, under which competency — and the roster of who was there.
 *  Each participant, including whoever creates it, writes their own account
 *  afterwards on the case page. */
export function NewCase({ onCreated }: { onCreated: (record: Case) => void }) {
  const { user } = useAuth()

  const [subjects, setSubjects] = useState<SubjectMeta[]>([])
  const [subject, setSubject] = useState<Subject>('Orthopaedics')
  const [narrative, setNarrative] = useState('')

  const [roles, setRoles] = useState<RoleOption[]>([])
  const [invited, setInvited] = useState<DopsRole[]>([])

  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [analysing, setAnalysing] = useState(false)
  const [waiting, setWaiting] = useState(0)
  const [transcribing, setTranscribing] = useState<{ seconds: number } | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [editing, setEditing] = useState(false)
  const [fix, setFix] = useState<{
    diagnosis: string
    procedure: string
    age: string
    sex: string
  } | null>(null)

  const [competencies, setCompetencies] = useState<Competency[]>([])
  const [competencyId, setCompetencyId] = useState<string>('')

  const analysedFor = useRef<string | null>(null)
  const textarea = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    getSubjects().then(setSubjects).catch(() => undefined)
    listRoles()
      .then((items) => setRoles(items.map(({ key, name, dops_role }) => ({ key, name, dops_role }))))
      .catch(() => setRoles([]))
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

  // You are always on your own case, so your row is shown but never offered.
  const others = roles.filter((option) => option.dops_role !== user?.dops_role)

  const analyse = useCallback(async () => {
    if (!ready || analysing) return
    if (analysedFor.current === key && analysis) return // nothing changed
    setAnalysing(true)
    setWaiting(0)
    setError(null)

    try {
      // The rules read lands in a tenth of a second and the AI's a few seconds
      // later, but this screen waits for the finished answer — opening early
      // meant values changing under the person checking them.
      const result = await parseEntryStream(subject, trimmed, { onWaiting: setWaiting })
      analysedFor.current = key
      setAnalysis(result)
      setFix({
        diagnosis: result.parsed.diagnosis?.display ?? '',
        procedure: result.parsed.procedure?.display ?? '',
        age: result.parsed.patient?.age ? String(result.parsed.patient.age) : '',
        sex: result.parsed.patient?.sex ?? '',
      })
      setCompetencyId(result.competency?.id ?? (competencies.length === 1 ? competencies[0].id : ''))
      setEditing(false)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not read this case')
    } finally {
      setAnalysing(false)
      setWaiting(0)
    }
  }, [ready, analysing, key, analysis, subject, trimmed, competencies])

  /** Dictation adds to the case, it does not take it over. */
  const appendDictated = useCallback((text: string) => {
    setNarrative((current) => {
      const joined = current.trim() ? `${current.trimEnd()} ${text}` : text
      return joined.length > MAX_NARRATIVE ? joined.slice(0, MAX_NARRATIVE).trimEnd() : joined
    })
    textarea.current?.focus()
  }, [])

  const patch = useCallback(
    (part: Partial<NonNullable<typeof fix>>) =>
      setFix((current) => (current ? { ...current, ...part } : current)),
    [],
  )

  const toggle = useCallback((role: DopsRole) => {
    setInvited((current) =>
      current.includes(role) ? current.filter((item) => item !== role) : [...current, role],
    )
  }, [])

  const save = useCallback(async () => {
    if (!reviewing || saving) return
    if (competencies.length > 1 && !competencyId) return
    setSaving(true)
    setError(null)
    try {
      onCreated(
        await createCase({
          subject,
          narrative: trimmed,
          participants: invited,
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
      setError(cause instanceof Error ? cause.message : 'Could not create this case')
      setSaving(false)
    }
  }, [reviewing, saving, subject, trimmed, invited, fix, competencyId, competencies.length, onCreated])

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
            Everything below was read from the case. Correct anything that is wrong — these
            fields are shared by everyone who logs against it.
          </p>
        </header>

        <section className="card review">
          <div className="review-competency">
            <span className="review-badge">
              <AiIcon width={13} height={13} />
              {aiPicked && analysis.source === 'corti' ? 'Competency identified by AI' : 'Competency'}
            </span>

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
                    ? 'Every reasoning exercise on this case is built on it. Change it if it is wrong.'
                    : 'Pick the competency this case is evidence for.'}
                </p>
              </>
            ) : (
              <h2 className="prose">
                {competencies[0]?.title ?? 'No competency set up for this speciality yet'}
              </h2>
            )}
          </div>

          <div className="review-fields-head">
            <span className="eyebrow">Fields read from the case</span>
            <button type="button" className="btn btn-quiet" onClick={() => setEditing((on) => !on)}>
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
                Corrections are saved with the case, and every reasoning exercise built on it
                uses the corrected version.
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
                  [
                    'In the room',
                    [user?.name, ...invited.map((r) => roles.find((o) => o.dops_role === r)?.name)]
                      .filter(Boolean)
                      .join(' · '),
                  ],
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
                <strong>The case does not document these.</strong> That is not an error — the
                reasoning exercises will ask about them.
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
            disabled={saving || (competencies.length > 1 && !competencyId)}
            onClick={save}
          >
            <CheckIcon width={16} height={16} />
            {saving ? 'Creating…' : 'Create case'}
          </button>
        </div>
      </div>
    )
  }

  /* ── step 1 · write the case ───────────────────────────────────────── */
  return (
    <div className="entry">
      <header className="entry-head">
        <span className="eyebrow">Step 1 of 2 · the shared case</span>
        <h1 className="entry-title">New case</h1>
        <p className="entry-lede">
          Write what happened, as everyone in the room would recognise it. You and each person
          you name add your own log afterwards — this is the case, not your account of it.
        </p>
      </header>

      <section className="card form">
        <div className="field-block">
          <label className="field-label" htmlFor="subject-tabs">
            Speciality
          </label>
          <div className="segmented" id="subject-tabs" role="radiogroup" aria-label="Speciality">
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
          <div className="field-label-row">
            <label className="field-label" htmlFor="narrative">
              {meta?.subject_class === 'pre-clinical' ? 'What was studied?' : 'What happened?'}
            </label>
            {canDictate() && (
              <Dictation
                onText={appendDictated}
                onBusy={(busy, seconds) => setTranscribing(busy ? { seconds } : null)}
                disabled={analysing}
              />
            )}
          </div>

          <div className={`textbox-wrap${transcribing ? ' is-busy' : ''}`}>
            <textarea
              id="narrative"
              ref={textarea}
              className="textbox prose"
              value={narrative}
              placeholder={PLACEHOLDER[meta?.subject_class ?? 'clinical']}
              spellCheck
              readOnly={transcribing !== null}
              aria-busy={transcribing !== null}
              onChange={(event) => setNarrative(event.target.value)}
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') void analyse()
              }}
            />
            {transcribing && <TranscribeLoader seconds={transcribing.seconds} />}
          </div>
          <div className="field-foot">
            <span className="field-help">
              <strong>Free text, not a form.</strong> What is left out is signal too.
            </span>
            <span className="field-count">
              {words} word{words === 1 ? '' : 's'}
            </span>
          </div>
        </div>

        <div className="field-block">
          <label className="field-label" htmlFor="roster">
            Who else worked on this case?
          </label>
          <div className="roster" id="roster">
            <div className="roster-me">
              <CheckIcon width={14} height={14} />
              <span>
                <strong>{user?.name}</strong>
                <small>you — always on your own case</small>
              </span>
            </div>

            {others.map((option) => {
              const on = invited.includes(option.dops_role)
              return (
                <button
                  key={option.key}
                  type="button"
                  role="checkbox"
                  aria-checked={on}
                  className={`roster-option${on ? ' is-on' : ''}`}
                  onClick={() => toggle(option.dops_role)}
                >
                  <span className="roster-box" aria-hidden>
                    {on && <CheckIcon width={12} height={12} />}
                  </span>
                  <span>{option.name}</span>
                </button>
              )
            })}
          </div>
          <p className="field-help">
            Each person named here can add their own log, and the professor writes a separate set
            of questions for each of them. Leave it empty if you worked alone.
          </p>
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
          {analysing
            ? waiting >= 3
              ? `Checking with AI… ${Math.round(waiting)}s`
              : 'Reading the case…'
            : 'Analyse case'}
          {!analysing && <ArrowIcon width={16} height={16} />}
        </button>
      </div>
    </div>
  )
}
