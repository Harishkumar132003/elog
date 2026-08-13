import { useCallback, useEffect, useRef, useState } from 'react'

import { ArrowIcon, CheckIcon, NodeIcon } from '../../components/icons'
import { Dictation, canDictate } from '../entry/Dictation'
import { TranscribeLoader } from '../entry/TranscribeLoader'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { addLog, deleteCase, getCaseRecord, listLogs } from '../../lib/cases'
import type { AuthUser, Case, Entry, Participant } from '../../types'
import '../entry/entry.css'
import './case.css'

const MIN_CHARS = 20
const MAX_NARRATIVE = 4000

/* Built but not exposed — set true to bring each back on the log form. */
const SHOW_LOG_GUIDANCE = false
const SHOW_DICTATION = false

const when = (value: string | null | undefined) =>
  value
    ? new Date(value).toLocaleString(undefined, {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
      })
    : null

interface CasePageProps {
  caseId: string
  user: AuthUser
  onChanged: () => void
  onOpenLog: (entryId: string) => void
  onBuild: (entryId: string) => void
  /** Open the exercise page — read it, or answer it. */
  onAnswer: (entryId: string) => void
  /** The case is gone; there is nothing left on this route. */
  onDeleted: () => void
}

/** One case: the shared facts, who was in it, and each person's own log.
 *
 *  Everything loads before anything renders. A roster that fills in row by row
 *  reads as the page correcting itself, and the professor's decision about
 *  whose questions to write depends on seeing the whole roster at once. */
export function CasePage({
  caseId,
  user,
  onChanged,
  onOpenLog,
  onBuild,
  onAnswer,
  onDeleted,
}: CasePageProps) {
  const [record, setRecord] = useState<Case | null>(null)
  const [logs, setLogs] = useState<Entry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [narrative, setNarrative] = useState('')
  const [saving, setSaving] = useState(false)
  const [transcribing, setTranscribing] = useState<{ seconds: number } | null>(null)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const textarea = useRef<HTMLTextAreaElement>(null)

  const load = useCallback(async () => {
    try {
      const [shared, written] = await Promise.all([getCaseRecord(caseId), listLogs(caseId)])
      setRecord(shared)
      setLogs(written)
      setError(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not load this case')
    } finally {
      setLoading(false)
    }
  }, [caseId])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    const node = textarea.current
    if (!node) return
    node.style.height = 'auto'
    node.style.height = `${Math.max(140, Math.min(node.scrollHeight, 380))}px`
  }, [narrative])

  const appendDictated = useCallback((text: string) => {
    setNarrative((current) => {
      const joined = current.trim() ? `${current.trimEnd()} ${text}` : text
      return joined.length > MAX_NARRATIVE ? joined.slice(0, MAX_NARRATIVE).trimEnd() : joined
    })
    textarea.current?.focus()
  }, [])

  const submit = useCallback(async () => {
    const trimmed = narrative.trim()
    if (trimmed.length < MIN_CHARS || saving) return
    setSaving(true)
    setError(null)
    try {
      await addLog(caseId, trimmed)
      setNarrative('')
      await load()
      onChanged()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save your log')
    } finally {
      setSaving(false)
    }
  }, [narrative, saving, caseId, load, onChanged])

  const remove = useCallback(async () => {
    if (deleting) return
    setDeleting(true)
    setError(null)
    try {
      await deleteCase(caseId)
      onDeleted()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not delete this case')
      setDeleting(false)
      setConfirmingDelete(false)
    }
  }, [caseId, deleting, onDeleted])

  if (loading) {
    return (
      <div className="case-boot">
        <div className="page-head">
          <div>
            <span className="eyebrow">Case</span>
            <h1 className="page-title">Loading…</h1>
          </div>
        </div>
        <div className="skeleton-card" />
        <div className="skeleton-card" />
      </div>
    )
  }

  if (!record) {
    return (
      <>
        <div className="page-head">
          <div>
            <span className="eyebrow">Case</span>
            <h1 className="page-title">Not available</h1>
          </div>
        </div>
        <p className="entry-error">{error ?? 'This case does not exist, or you were not in it.'}</p>
      </>
    )
  }

  const isProfessor = user.role === 'professor'
  const mine = record.participants.find((p) => p.user_id === user.id)
  const canLog = mine != null && mine.entry_id == null
  const trimmed = narrative.trim()
  const words = trimmed ? trimmed.split(/\s+/).length : 0
  const logged = record.participants.filter((p) => p.entry_id).length

  return (
    <div className="case">
      <header className="page-head">
        <div>
          <span className="eyebrow">
            {record.subject} · {logged} of {record.participants.length} logged
          </span>
          <h1 className="page-title">{record.diagnosis ?? 'Case'}</h1>
        </div>
        <button
          type="button"
          className="btn btn-quiet btn-danger"
          onClick={() => setConfirmingDelete(true)}
        >
          Delete case
        </button>
      </header>

      {/* ── the shared facts ──────────────────────────────────────────── */}
      <section className="card case-facts">
        {record.competency_title && (
          <p className="case-competency">
            <NodeIcon width={14} height={14} />
            {record.competency_title}
          </p>
        )}

        <dl className="case-strip">
          {(
            [
              ['Diagnosis', record.diagnosis],
              ['Procedure', record.procedure],
              [
                'Patient',
                [record.patient_age, record.patient_sex].filter(Boolean).join(' · ') || null,
              ],
              ['Created', when(record.created_at)],
            ] as const
          ).map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd className={value ? '' : 'is-blank'}>{value ?? 'not stated'}</dd>
            </div>
          ))}
        </dl>

        <div className="case-narrative">
          <span className="eyebrow">What happened</span>
          <p className="prose">{record.narrative}</p>
        </div>
      </section>

      {/* ── your own log ──────────────────────────────────────────────── */}
      {canLog && (
        <section className="card case-mine">
          <header className="case-mine-head">
            <div>
              <span className="eyebrow">Your log · {mine?.role_label}</span>
              <h2 className="case-h2">Add your own account</h2>
            </div>
          </header>
          {SHOW_LOG_GUIDANCE && (
            <p className="case-lede">
              The clinical facts are above and shared. Record what <em>you</em> did in this
              case — your part in it, in order. Leave the reasoning out: that is what the
              questions will ask you for.
            </p>
          )}

          {(SHOW_LOG_GUIDANCE || SHOW_DICTATION) && (
            <div className="field-label-row">
              {SHOW_LOG_GUIDANCE && <span className="field-label">Your account</span>}
              {SHOW_DICTATION && canDictate() && (
                <Dictation
                  onText={appendDictated}
                  onBusy={(busy, seconds) => setTranscribing(busy ? { seconds } : null)}
                  disabled={saving}
                />
              )}
            </div>
          )}

          <div className={`textbox-wrap${transcribing ? ' is-busy' : ''}`}>
            <textarea
              ref={textarea}
              className="textbox prose"
              value={narrative}
              placeholder="e.g. Scrubbed in as second assistant. Held retraction for the mobilisation, took the specimen for histology, assisted with the washout and the closure."
              spellCheck
              readOnly={transcribing !== null}
              aria-busy={transcribing !== null}
              aria-label="Your account of this case"
              onChange={(event) => setNarrative(event.target.value)}
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') void submit()
              }}
            />
            {transcribing && <TranscribeLoader seconds={transcribing.seconds} />}
          </div>

          <div className="field-foot">
            <span className="field-help">
              Saved with the date and time you write it — not when the case was created.
            </span>
            <span className="field-count">
              {words} word{words === 1 ? '' : 's'}
            </span>
          </div>

          {error && <p className="entry-error">{error}</p>}

          <div className="case-mine-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={trimmed.length < MIN_CHARS || saving}
              onClick={submit}
            >
              {saving ? 'Saving…' : 'Save my log'}
              {!saving && <ArrowIcon width={16} height={16} />}
            </button>
            {trimmed.length < MIN_CHARS && (
              <span className="case-hint">Write at least {MIN_CHARS} characters.</span>
            )}
          </div>
        </section>
      )}

      {/* ── the roster ────────────────────────────────────────────────── */}
      <section className="card case-roster">
        <header className="case-roster-head">
          <span className="eyebrow">Who was in this case</span>
          <p className="case-lede">
            {isProfessor
              ? 'Each log gets its own set of questions — the role decides which variations are worth asking.'
              : 'Everyone here logs the same case in their own words. Only your professor reads the others.'}
          </p>
        </header>

        <ul className="roster-list">
          {record.participants.map((participant) => (
            <RosterRow
              key={participant.user_id}
              participant={participant}
              log={logs.find((entry) => entry.resident_id === participant.user_id)}
              isMe={participant.user_id === user.id}
              isProfessor={isProfessor}
              onOpen={onOpenLog}
              onBuild={onBuild}
              onAnswer={onAnswer}
            />
          ))}
        </ul>
      </section>

      {confirmingDelete && (
        <ConfirmDialog
          danger
          busy={deleting}
          title="Delete this case?"
          lede={record.diagnosis ?? 'This case'}
          points={[
            `Every log on it goes — ${record.participants.filter((p) => p.has_logged).length} written so far.`,
            'So does everything built on those logs: the questions, the marks and the recorded results.',
            'Anyone else on this case loses their log and their exercise too.',
            'This cannot be undone.',
          ]}
          confirmLabel="Delete the case"
          cancelLabel="Keep it"
          onConfirm={() => void remove()}
          onCancel={() => setConfirmingDelete(false)}
        />
      )}
    </div>
  )
}

function RosterRow({
  participant,
  log,
  isMe,
  isProfessor,
  onOpen,
  onBuild,
  onAnswer,
}: {
  participant: Participant
  log: Entry | undefined
  isMe: boolean
  isProfessor: boolean
  onOpen: (entryId: string) => void
  onBuild: (entryId: string) => void
  onAnswer: (entryId: string) => void
}) {
  const [open, setOpen] = useState(false)
  // Whether they logged is roster; whether *you* may open it is not. The server
  // withholds `entry_id` for other people's rows, so there is nothing to open.
  const written = participant.has_logged
  const mayOpen = participant.entry_id != null
  // The exercise has been attempted. Every label below turns on this: a button
  // still saying "Answer your exercise" after it has been answered sends the
  // person back to a screen with nothing left to do on it.
  const answered = participant.status === 'answered'

  return (
    <li className={`roster-row${written ? '' : ' is-waiting'}`}>
      <div className="roster-row-main">
        <span className={`roster-dot${written ? ' is-done' : ''}`} aria-hidden>
          {written ? <CheckIcon width={12} height={12} /> : null}
        </span>

        <div className="roster-row-text">
          <strong>
            {participant.role_label}
            {isMe && <span className="roster-you">you</span>}
            {participant.is_creator && <span className="roster-tag">created the case</span>}
          </strong>
          <small>
            {!written
              ? 'Has not written their log yet'
              : !mayOpen
                ? // Someone else's row. That they have logged is roster; what
                  // they wrote, and how it was marked, is theirs.
                  `Logged ${when(participant.logged_at)} · private to them`
                : `Logged ${when(participant.logged_at)}${
                    participant.questions
                      ? ` · ${participant.questions} question${participant.questions === 1 ? '' : 's'}${
                          answered
                            ? ' · answered'
                            : participant.released
                              ? ' · released'
                              : ' · draft'
                        }`
                      : ' · no questions yet'
                  }`}
          </small>
        </div>

        <div className="roster-row-actions">
          {written && log && (
            <button type="button" className="btn btn-quiet btn-sm" onClick={() => setOpen((on) => !on)}>
              {open ? 'Hide' : 'Read'}
            </button>
          )}
          {/* Once released the exercise is frozen — the API refuses edits with a
              409 — so the builder is only offered while it can still be used. */}
          {written && mayOpen && isProfessor && (
            <>
              {participant.questions > 0 && !participant.released && (
                <button
                  type="button"
                  className="btn btn-quiet btn-sm"
                  onClick={() => onBuild(participant.entry_id as string)}
                >
                  Edit questions
                </button>
              )}
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() =>
                  participant.questions === 0
                    ? onBuild(participant.entry_id as string)
                    : onAnswer(participant.entry_id as string)
                }
              >
                {participant.questions === 0
                  ? 'Build questions'
                  : answered
                    ? 'View result'
                    : participant.released
                      ? 'View exercise'
                      : 'Review & release'}
              </button>
            </>
          )}

          {written && mayOpen && !isProfessor && isMe && (
            <button
              type="button"
              className={`btn btn-sm ${
                // Loud only when there is something outstanding to do.
                participant.released && !answered ? 'btn-primary' : 'btn-quiet'
              }`}
              onClick={() =>
                participant.released
                  ? onAnswer(participant.entry_id as string)
                  : onOpen(participant.entry_id as string)
              }
            >
              {answered
                ? 'View your result'
                : participant.released
                  ? 'Answer your exercise'
                  : 'Open'}
            </button>
          )}
        </div>
      </div>

      {open && log && <p className="roster-row-log prose">{log.narrative}</p>}
    </li>
  )
}
