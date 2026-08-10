import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { AlertIcon, CheckIcon } from '../../components/icons'
import { getDashboard } from '../../lib/entries'
import type { Dashboard as DashboardData, EntryStatus } from '../../types'
import { CoverageDialog } from './CoverageDialog'
import './dashboard.css'

const formatDate = new Intl.DateTimeFormat(undefined, { day: '2-digit', month: 'short' })

/** Same wording the logbook uses, so a stage means one thing everywhere. */
const STAGE_LABEL: Record<EntryStatus, string> = {
  logged: 'Awaiting certification',
  certified: 'Questions in review',
  released: 'Ready to answer',
  answered: 'Reasoned',
}

const OUTCOME_TONE: Record<string, string> = {
  Satisfactory: 'is-ok',
  Borderline: 'is-warn',
  Unsatisfactory: 'is-weak',
  'Critical failure': 'is-alert',
}

/** A result pill takes its tone from the outcome, so a poor score never reads
 *  as a pass just because it cleared the Critical item. */
const OUTCOME_PILL: Record<string, string> = {
  Satisfactory: 'pill-ok',
  Borderline: 'pill-warm',
  Unsatisfactory: '',
  'Critical failure': 'pill-alert',
}

/** A single-series magnitude bar: length plus the printed value carry it, so
 *  colour never has to be read on its own. */
function Meter({ value, tone = 'accent' }: { value: number; tone?: 'accent' | 'warm' }) {
  // A small non-zero value still gets a visible stub, but zero draws nothing —
  // a sliver where there is no evidence reads as "a little", which is a lie.
  const width = value <= 0 ? 0 : Math.max(value, 1.5)
  return (
    <div className="meter" role="presentation">
      <div className={`meter-fill is-${tone}`} style={{ width: `${width}%` }} />
    </div>
  )
}

/** Evidence is not binary. One logged case and five are both "covered" on a
 *  ratio, and they are not the same thing to an examiner. */
function depth(cases: number): string {
  if (cases >= 5) return 'is-solid'
  if (cases >= 3) return 'is-mid'
  return 'is-thin'
}

/** A curriculum can run past a hundred competencies; past this the grid stops
 *  being a glance and the count carries it instead. */
const MAX_SQUARES = 72

/** One square per competency in the subject.
 *
 *  Replaces a percentage bar, which was actively misleading: 2 of 15 drew a
 *  near-empty bar that read as failure, when it is simply what eleven cases look
 *  like against a full curriculum. Squares show the same ratio without implying
 *  a target, and they make the *scale* visible — that Orthopaedics carries 23
 *  competencies and Pathology one is the thing a ratio hides completely.
 */
function Squares({ row }: { row: DashboardData['coverage'][number] }) {
  if (row.total === 0) {
    return <p className="coverage-note">No competencies set up for this subject yet.</p>
  }

  // Retired competencies still show in the list beneath — the cases happened —
  // but they are no longer part of the curriculum, so they get no square.
  const live = row.competencies.filter((c) => !c.retired).slice(0, MAX_SQUARES)
  const empty = Math.max(Math.min(row.total, MAX_SQUARES) - live.length, 0)
  const hidden = Math.max(row.total - MAX_SQUARES, 0)

  return (
    <>
      <div className="squares" role="img" aria-label={`${row.covered} of ${row.total} competencies have evidence`}>
        {live.map((item) => (
          <span
            key={item.id}
            className={`square ${depth(item.logged)}`}
            title={`${item.title} — ${item.logged} case${item.logged === 1 ? '' : 's'}`}
          />
        ))}
        {Array.from({ length: empty }, (_, i) => (
          <span key={`empty-${i}`} className="square" />
        ))}
      </div>
      {hidden > 0 && <p className="coverage-note">+{hidden} more with no evidence</p>}
      {/* A single competency is the seed, not a curriculum. Said briefly because
          it repeats on every subject the professor has not loaded yet. */}
      {row.total === 1 && <p className="coverage-note">Curriculum not loaded yet</p>}
    </>
  )
}

function Panel({
  eyebrow,
  title,
  note,
  className = '',
  children,
}: {
  eyebrow: string
  title: string
  note?: string
  className?: string
  children: React.ReactNode
}) {
  return (
    <section className={`card dash-panel ${className}`.trim()}>
      <header>
        <span className="eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
        {note && <p>{note}</p>}
      </header>
      {children}
    </section>
  )
}

export function Dashboard() {
  const navigate = useNavigate()
  const [data, setData] = useState<DashboardData | null>(null)
  const [resident, setResident] = useState<string | null>(null)
  const [openSubject, setOpenSubject] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let live = true
    setLoading(true)
    getDashboard(resident)
      .then((result) => live && setData(result))
      .catch(() => undefined)
      .finally(() => live && setLoading(false))
    return () => {
      live = false
    }
  }, [resident])

  if (!data) return <div className="flow-loading">{loading ? 'Loading…' : 'No data'}</div>

  // A plain count, not a ratio: "8 of 205" for a resident with ten cases reads as
  // catastrophic when it is simply what ten cases look like against a full
  // curriculum. The per-subject meters below carry the ratio, where it means something.
  const covered = data.coverage.reduce((n, row) => n + row.covered, 0)
  const subjectsStarted = data.coverage.filter((row) => row.covered > 0).length
  const who = data.residents.find((r) => r.id === resident)
  const empty = data.totals.cases === 0
  const openRow = data.coverage.find((row) => row.subject === openSubject) ?? null

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Supervision</span>
          <h1 className="page-title">{who ? who.name : 'All residents'}</h1>
        </div>
        <p className="page-sub">
          What the logbook says about {who ? 'this resident' : 'your residents'} — coverage,
          safety, and the habits behind the marks.
        </p>
      </div>

      <div className="dash-filter">
        <label htmlFor="resident-filter">Showing</label>
        <select
          id="resident-filter"
          className="select"
          value={resident ?? ''}
          onChange={(event) => setResident(event.target.value || null)}
        >
          <option value="">
            All residents ({data.residents.reduce((n, r) => n + r.cases, 0)} cases)
          </option>
          {data.residents.map((person) => (
            <option key={person.id} value={person.id}>
              {person.name} ({person.cases} case{person.cases === 1 ? '' : 's'})
            </option>
          ))}
        </select>
        {loading && <span className="dash-filter-busy">updating…</span>}
      </div>

      {empty ? (
        <div className="card stage-empty">
          <p>{who ? `${who.name} has not logged any cases yet.` : 'No cases logged yet.'}</p>
        </div>
      ) : (
        <>
          {/* headline — plain numbers, no chart needed */}
          <div className="tiles">
            <div className="tile">
              <strong>{data.totals.cases}</strong>
              <span>cases logged</span>
            </div>
            <div className={`tile${data.totals.awaiting_certification ? ' is-warn' : ''}`}>
              <strong>{data.totals.awaiting_certification}</strong>
              <span>awaiting your certification</span>
            </div>
            <div className={`tile${data.critical_failed ? ' is-alert' : ''}`}>
              <strong>{data.critical_failed}</strong>
              <span>
                critical failure{data.critical_failed === 1 ? '' : 's'} in {data.attempts}{' '}
                attempt{data.attempts === 1 ? '' : 's'}
              </span>
            </div>
            <div className="tile">
              <strong>{covered}</strong>
              <span>
                competenc{covered === 1 ? 'y' : 'ies'} with evidence, across{' '}
                {subjectsStarted} subject{subjectsStarted === 1 ? '' : 's'}
              </span>
            </div>
          </div>

          <div className="dash-grid">
            <Panel
              eyebrow="Coverage"
              title="Competencies with evidence"
              note="One square per competency in the curriculum. Filled squares have logged
                    cases; the shade is how many."
            >
              <ul className="coverage">
                {data.coverage.map((row) => (
                  <li key={row.subject} className={row.covered ? '' : 'is-gap'}>
                    {/* The whole row opens the detail — the squares are a summary,
                        and the names live in the dialog where there is room. */}
                    <button
                      type="button"
                      className="coverage-open"
                      onClick={() => setOpenSubject(row.subject)}
                      aria-label={`${row.subject} — ${row.covered} of ${row.total} competencies with evidence. Open the full list.`}
                    >
                      <span className="coverage-head">
                        <span className="coverage-subject">
                          <span className="coverage-mark" aria-hidden>
                            {row.covered ? (
                              <CheckIcon width={12} height={12} />
                            ) : (
                              <AlertIcon width={12} height={12} />
                            )}
                          </span>
                          <strong>{row.subject}</strong>
                        </span>
                        <span className="coverage-count">
                          {row.total === 0 ? 'none set up' : `${row.covered} of ${row.total}`}
                        </span>
                      </span>

                      <Squares row={row} />
                    </button>
                  </li>
                ))}
              </ul>

              <p className="coverage-key">
                <span className="square is-solid" aria-hidden /> 5+ cases
                <span className="square is-mid" aria-hidden /> 3–4
                <span className="square is-thin" aria-hidden /> 1–2
                <span className="square" aria-hidden /> none yet
                <span className="coverage-key-hint">Select a subject for the full list</span>
              </p>
            </Panel>

            <Panel
              eyebrow="Reasoning"
              title="Where marks are lost"
              note="Marks earned when the case is varied along each axis, weakest first."
            >
              {data.axes.length === 0 ? (
                <p className="dash-empty">No exercises marked yet.</p>
              ) : (
                <ul className="bars">
                  {data.axes.map((axis) => (
                    <li key={axis.axis_id}>
                      <div className="bar-head">
                        <span className="bar-label">
                          <strong>{axis.label}</strong>
                          <small>{axis.family}</small>
                        </span>
                        <span className="bar-value">
                          {axis.percentage}%
                          <em>
                            {axis.awarded}/{axis.available}
                          </em>
                        </span>
                      </div>
                      <Meter value={axis.percentage} />
                    </li>
                  ))}
                </ul>
              )}
            </Panel>

            <Panel
              className="dash-wide"
              eyebrow="Metrics"
              title="Cognitive reach"
              note="Reasoning questions should land on Apply, Analyse and Evaluate (§3.1)."
            >
              <ul className="levels">
                {data.cognitive.map((row) => (
                  <li
                    key={row.level}
                    className={`${row.target ? 'is-target' : ''}${row.asked ? '' : ' is-idle'}`}
                  >
                    <span>{row.level}</span>
                    <span className="levels-count">
                      {row.asked ? `${row.correct}/${row.asked} correct` : '—'}
                    </span>
                  </li>
                ))}
              </ul>

              {data.outcomes.length > 0 && (
                <div className="outcomes">
                  <span className="eyebrow">Recorded results</span>
                  <ul>
                    {data.outcomes.map((row) => (
                      <li key={row.key} className={OUTCOME_TONE[row.label] ?? ''}>
                        {row.label}
                        <em>{row.count}</em>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Panel>
          </div>

          <section className="card table-card dash-log">
            <header className="dash-log-head">
              <div>
                <span className="eyebrow">Recent</span>
                <h2>
                  Latest {data.recent.length} of {data.totals.cases} cases
                </h2>
              </div>
              <button type="button" className="btn btn-quiet" onClick={() => navigate('/cases')}>
                View the full log
              </button>
            </header>
            <table className="table">
              <thead>
                <tr>
                  {!resident && <th>Resident</th>}
                  <th>Case</th>
                  <th>Stage</th>
                  <th className="num">Result</th>
                  <th className="num col-optional">Logged</th>
                </tr>
              </thead>
              <tbody>
                {data.recent.map((row) => (
                  <tr
                    key={row.id}
                    className="row-clickable"
                    onClick={() => navigate(`/cases/${row.id}`)}
                  >
                    {!resident && <td className="strong">{row.resident_name ?? '—'}</td>}
                    <td>
                      <span className="cell-title">{row.diagnosis ?? row.subject}</span>
                      <span className="cell-sub">{row.competency_title}</span>
                    </td>
                    <td>
                      <span className="pill">{STAGE_LABEL[row.status] ?? row.status}</span>
                    </td>
                    <td className="num">
                      {row.outcome ? (
                        <span
                          className={`pill ${
                            row.critical_failed
                              ? 'pill-alert'
                              : (OUTCOME_PILL[row.outcome] ?? '')
                          }`}
                        >
                          {row.percentage}% · {row.outcome}
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="num col-optional">
                      {formatDate.format(new Date(row.created_at))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}

      {openRow && <CoverageDialog row={openRow} onClose={() => setOpenSubject(null)} />}
    </>
  )
}
