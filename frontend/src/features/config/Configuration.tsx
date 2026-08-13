import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { AiIcon, AlertIcon, CheckIcon } from '../../components/icons'
import { getCatalogue, getImport, saveCatalogue, startImport } from '../../lib/config'
import { forgetCompetencies } from '../../lib/entries'
import type { Competency, ImportJob, Subject } from '../../types'
import './config.css'

const SUBJECTS: Subject[] = [
  'General Surgery',
  'Orthopaedics',
  'Pathology',
  'Forensic Medicine',
  'Physiology',
]

const POLL_MS = 1500
const MAX_TITLE = 220

/** A row being edited. `id` is null until the row has been saved once. */
interface Row {
  key: string
  id: string | null
  title: string
  fromPdf: boolean
}

let rowSeq = 0
const nextKey = () => `row-${++rowSeq}`

const toRow = (item: Competency): Row => ({
  key: nextKey(),
  id: item.id,
  title: item.title,
  fromPdf: false,
})

const formatDate = new Intl.DateTimeFormat(undefined, {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})

export function Configuration() {
  const [subject, setSubject] = useState<Subject>('General Surgery')
  const [rows, setRows] = useState<Row[]>([])
  const [saved, setSaved] = useState<Row[]>([])
  const [editor, setEditor] = useState<{ at: string | null; by: string | null }>({
    at: null,
    by: null,
  })

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const [file, setFile] = useState<File | null>(null)
  const [job, setJob] = useState<ImportJob | null>(null)
  const [importing, setImporting] = useState(false)

  const fileInput = useRef<HTMLInputElement>(null)

  const load = useCallback(async (which: Subject) => {
    setLoading(true)
    setError(null)
    setNote(null)
    try {
      const data = await getCatalogue(which)
      const loaded = data.items.map(toRow)
      setRows(loaded)
      setSaved(loaded)
      setEditor({ at: data.updated_at, by: data.updated_by })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not load the catalogue')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    setJob(null)
    setFile(null)
    if (fileInput.current) fileInput.current.value = ''
    void load(subject)
  }, [subject, load])

  /* ── the import job ──────────────────────────────────────────────────── */
  useEffect(() => {
    if (!job || job.status !== 'running') return
    let live = true
    const timer = setInterval(async () => {
      try {
        const next = await getImport(job.id)
        if (!live) return
        setJob(next)
        if (next.status !== 'running') setImporting(false)
        if (next.status === 'done') {
          // Extracted rows join the list the professor is already editing, badged
          // as new. Nothing is saved until they press Save.
          setRows((current) => [
            ...current,
            ...next.found.map((title) => ({
              key: nextKey(),
              id: null,
              title,
              fromPdf: true,
            })),
          ])
          setNote(
            next.found.length
              ? `Found ${next.found.length} competenc${next.found.length === 1 ? 'y' : 'ies'} not already on the list. Check them, then save.`
              : 'Nothing new in that PDF — everything it lists is already on this speciality.',
          )
        }
      } catch (cause) {
        if (!live) return
        setImporting(false)
        setError(cause instanceof Error ? cause.message : 'Lost track of that import')
      }
    }, POLL_MS)
    return () => {
      live = false
      clearInterval(timer)
    }
  }, [job])

  async function extract() {
    if (!file || importing) return
    setImporting(true)
    setError(null)
    setNote(null)
    try {
      const started = await startImport(subject, file)
      setJob({
        id: started.job_id,
        subject,
        status: 'running',
        filename: file.name,
        done: 0,
        total: started.chunks,
        pages_read: started.pages_read,
        pages_total: started.pages_total,
        truncated: false,
        found: [],
        error: null,
      })
    } catch (cause) {
      setImporting(false)
      setError(cause instanceof Error ? cause.message : 'Could not read that PDF')
    }
  }

  /* ── editing ─────────────────────────────────────────────────────────── */
  const patch = useCallback((key: string, title: string) => {
    setRows((current) => current.map((row) => (row.key === key ? { ...row, title } : row)))
  }, [])

  const drop = useCallback((key: string) => {
    setRows((current) => current.filter((row) => row.key !== key))
  }, [])

  function add() {
    setRows((current) => [...current, { key: nextKey(), id: null, title: '', fromPdf: false }])
  }

  const dirty = useMemo(
    () =>
      JSON.stringify(rows.map((r) => [r.id, r.title.trim()])) !==
      JSON.stringify(saved.map((r) => [r.id, r.title.trim()])),
    [rows, saved],
  )

  const blank = rows.filter((row) => row.title.trim().length < 3).length
  const removed = saved.filter((row) => !rows.some((r) => r.id === row.id)).length
  const added = rows.filter((row) => row.id === null && row.title.trim()).length

  // Two identical statements would give the AI an impossible choice between them.
  const duplicates = useMemo(() => {
    const seen = new Map<string, number>()
    for (const row of rows) {
      const key = row.title.trim().toLowerCase().replace(/[^a-z0-9]+/g, '')
      if (key) seen.set(key, (seen.get(key) ?? 0) + 1)
    }
    return new Set([...seen].filter(([, n]) => n > 1).map(([key]) => key))
  }, [rows])

  const isDuplicate = (title: string) =>
    duplicates.has(title.trim().toLowerCase().replace(/[^a-z0-9]+/g, ''))

  async function save() {
    if (saving || blank > 0) return
    setSaving(true)
    setError(null)
    setNote(null)
    try {
      const result = await saveCatalogue(
        subject,
        rows
          .filter((row) => row.title.trim())
          .map((row) => ({
            id: row.id,
            title: row.title.trim(),
            source: row.fromPdf ? ('pdf' as const) : ('manual' as const),
          })),
      )
      const fresh = result.items.map(toRow)
      setRows(fresh)
      setSaved(fresh)
      // The entry screen's dropdown must not keep offering the old list.
      forgetCompetencies(subject)
      setNote(
        [
          result.added && `${result.added} added`,
          result.updated && `${result.updated} reworded`,
          result.removed && `${result.removed} removed`,
        ]
          .filter(Boolean)
          .join(' · ') || 'Nothing changed',
      )
      setEditor({ at: new Date().toISOString(), by: null })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save the catalogue')
    } finally {
      setSaving(false)
    }
  }

  const running = job?.status === 'running'
  const progress = job && job.total ? Math.round((job.done / job.total) * 100) : 0

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Setup</span>
          <h1 className="page-title">Configuration</h1>
        </div>
        <p className="page-sub">
          The competencies every resident logs against. Shared by all professors
          {editor.by ? ` · last changed by ${editor.by}` : ''}
          {editor.at ? ` on ${formatDate.format(new Date(editor.at))}` : ''}.
        </p>
      </div>

      <div className="cfg-subject">
        <label htmlFor="cfg-subject-select">Speciality</label>
        <select
          id="cfg-subject-select"
          className="select"
          value={subject}
          onChange={(event) => setSubject(event.target.value as Subject)}
        >
          {SUBJECTS.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
        <span className="cfg-count">
          {rows.length} competenc{rows.length === 1 ? 'y' : 'ies'}
        </span>
      </div>

      {/* ── import ─────────────────────────────────────────────────────── */}
      <section className="card cfg-import">
        <header>
          <span className="eyebrow">Import</span>
          <h2>Read them from a curriculum PDF</h2>
          <p>
            The AI lists the competency statements it finds and adds them below for you to
            check. Nothing is saved until you press Save.
          </p>
        </header>

        <div className="cfg-import-row">
          <input
            ref={fileInput}
            type="file"
            accept="application/pdf,.pdf"
            className="cfg-file"
            aria-label="Curriculum PDF"
            disabled={running}
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null)
              setNote(null)
            }}
          />
          <button
            type="button"
            className="btn btn-primary"
            disabled={!file || running}
            onClick={extract}
          >
            <AiIcon width={15} height={15} />
            {running ? 'Reading…' : 'Extract competencies'}
          </button>
        </div>

        {job && (
          <div className={`cfg-job${job.status === 'failed' ? ' is-failed' : ''}`}>
            {running ? (
              <>
                <div className="meter" role="presentation">
                  <div className="meter-fill is-accent" style={{ width: `${Math.max(progress, 3)}%` }} />
                </div>
                <p>
                  Reading excerpt {job.done} of {job.total}
                  {job.pages_total ? ` · ${job.pages_read} of ${job.pages_total} pages` : ''}
                </p>
              </>
            ) : job.status === 'failed' ? (
              <p>
                <AlertIcon width={14} height={14} />
                {job.error}
              </p>
            ) : (
              <p>
                <CheckIcon width={14} height={14} />
                Read {job.pages_read} page{job.pages_read === 1 ? '' : 's'} of {job.filename} ·{' '}
                {job.found.length} new
                {/* Never let a partial read pass for a complete one. */}
                {job.truncated &&
                  ` · that PDF was longer than the import limit, so only the first ${job.pages_read} pages were read`}
              </p>
            )}
          </div>
        )}
      </section>

      {/* ── the list ───────────────────────────────────────────────────── */}
      <section className="card cfg-list">
        <header className="panel-head">
          <div>
            <span className="eyebrow">Catalogue</span>
            <h2 className="panel-title">{subject}</h2>
          </div>
          <button type="button" className="btn btn-quiet" onClick={add}>
            Add competency
          </button>
        </header>

        {loading ? (
          <p className="cfg-empty">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="cfg-empty">
            No competencies for {subject} yet. Import a PDF above, or add them one at a time.
          </p>
        ) : (
          <ol className="cfg-rows">
            {rows.map((row, index) => {
              const value = row.title.trim()
              const duplicate = value.length > 0 && isDuplicate(row.title)
              return (
                <li key={row.key} className={duplicate ? 'is-duplicate' : ''}>
                  <span className="cfg-num">{index + 1}</span>
                  <div className="cfg-field">
                    <input
                      type="text"
                      value={row.title}
                      maxLength={MAX_TITLE}
                      placeholder="What the resident must be able to do"
                      aria-label={`Competency ${index + 1}`}
                      onChange={(event) => patch(row.key, event.target.value)}
                    />
                    {duplicate && <small className="cfg-warn">Already on this list</small>}
                  </div>
                  {row.fromPdf && row.id === null && <span className="pill pill-accent">from PDF</span>}
                  <button
                    type="button"
                    className="cfg-drop"
                    title="Remove this competency"
                    onClick={() => drop(row.key)}
                  >
                    Remove
                  </button>
                </li>
              )
            })}
          </ol>
        )}

        <div className="panel-foot">
          <p className={`panel-status${error ? ' is-error' : ''}`}>
            {error ??
              (blank
                ? `${blank} row${blank === 1 ? '' : 's'} still empty`
                : dirty
                  ? [added && `${added} new`, removed && `${removed} removed`]
                      .filter(Boolean)
                      .join(' · ') || 'Unsaved changes'
                  : (note ??
                    'Removing a competency keeps the cases already logged against it.'))}
          </p>
          <div className="panel-actions">
            <button
              type="button"
              className="btn btn-quiet"
              disabled={!dirty || saving}
              onClick={() => setRows(saved)}
            >
              Discard
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={!dirty || saving || blank > 0}
              onClick={save}
            >
              {saving ? 'Saving…' : 'Save catalogue'}
            </button>
          </div>
        </div>
      </section>
    </>
  )
}
