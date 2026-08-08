import { memo, useMemo, useState } from 'react'

import type { AuthUser, Entry, EntryStatus } from '../../types'
import { EmptyState } from './EmptyState'

const formatDate = new Intl.DateTimeFormat(undefined, { day: '2-digit', month: 'short' })

/** Age and sex are all the entry carries — narratives are de-identified. */
function patientOf(entry: Entry): string {
  const parts = [
    entry.patient_age ? String(entry.patient_age) : null,
    entry.patient_sex ?? null,
  ].filter(Boolean)
  return parts.length ? parts.join(' · ') : '—'
}

const STATUS: Record<EntryStatus, { label: string; className: string }> = {
  logged: { label: 'Awaiting certification', className: '' },
  certified: { label: 'Questions in review', className: '' },
  released: { label: 'Ready to answer', className: 'pill-warm' },
  answered: { label: 'Reasoned', className: 'pill-ok' },
}

/** In pipeline order, so the tabs read as the journey a case takes. */
const STAGES: EntryStatus[] = ['logged', 'certified', 'released', 'answered']

type Filter = EntryStatus | 'all'

interface Props {
  entries: readonly Entry[]
  residentNames: Map<string, string>
  user: AuthUser
  loading: boolean
  title?: string
  eyebrow?: string
  blurb?: string
  /** The queue is already filtered to one stage, so it hides the tabs. */
  showStageFilter?: boolean
  onOpen: (entryId: string) => void
  onNew?: () => void
}

function LogbookBase({
  entries,
  residentNames,
  user,
  loading,
  title,
  eyebrow,
  blurb,
  showStageFilter = true,
  onOpen,
  onNew,
}: Props) {
  const isProfessor = user.role === 'professor'
  const [filter, setFilter] = useState<Filter>('all')

  const counts = useMemo(() => {
    const tally = { all: entries.length } as Record<Filter, number>
    for (const stage of STAGES) tally[stage] = 0
    for (const entry of entries) tally[entry.status] = (tally[entry.status] ?? 0) + 1
    return tally
  }, [entries])

  const visible = useMemo(
    () => (filter === 'all' ? entries : entries.filter((entry) => entry.status === filter)),
    [entries, filter],
  )

  const showTabs = showStageFilter && !loading && entries.length > 0

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">{eyebrow ?? (isProfessor ? 'Supervision' : 'Logbook')}</span>
          <h1 className="page-title">{title ?? 'All cases'}</h1>
        </div>
        <p className="page-sub">
          {loading
            ? 'Loading…'
            : (blurb ??
              `${visible.length} of ${entries.length} case${entries.length === 1 ? '' : 's'} ${
                isProfessor ? 'across your residents' : 'recorded'
              }.`)}
        </p>
      </div>

      {showTabs && (
        <div className="stage-tabs" role="tablist" aria-label="Filter by stage">
          {(['all', ...STAGES] as Filter[]).map((stage) => (
            <button
              key={stage}
              type="button"
              role="tab"
              aria-selected={filter === stage}
              className={`stage-tab${filter === stage ? ' is-on' : ''}`}
              onClick={() => setFilter(stage)}
            >
              {stage === 'all' ? 'All' : STATUS[stage].label}
              <em>{counts[stage] ?? 0}</em>
            </button>
          ))}
        </div>
      )}

      {!loading && entries.length === 0 ? (
        <EmptyState
          title="Nothing here yet"
          body={
            isProfessor
              ? 'Cases logged by your residents appear here for certification.'
              : 'Cases you log appear here, and follow through to a reasoning exercise.'
          }
          action={onNew ? { label: 'Log a case', onClick: onNew } : undefined}
        />
      ) : visible.length === 0 ? (
        <div className="card stage-empty">
          <p>No cases at this stage.</p>
          <button type="button" className="btn btn-quiet" onClick={() => setFilter('all')}>
            Show all {entries.length}
          </button>
        </div>
      ) : (
        <div className="card table-card">
          <table className="table">
            <thead>
              <tr>
                {isProfessor && <th>Resident</th>}
                <th>Case</th>
                <th className="col-tight">Patient</th>
                <th className="col-optional">Role</th>
                <th>Stage</th>
                <th className="num col-optional">Logged</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((entry) => {
                const status = STATUS[entry.status]
                return (
                  <tr key={entry.id} className="row-clickable" onClick={() => onOpen(entry.id)}>
                    {isProfessor && (
                      <td className="strong">{residentNames.get(entry.resident_id) ?? '—'}</td>
                    )}
                    <td>
                      <span className="cell-title">{entry.diagnosis ?? entry.subject}</span>
                      <span className="cell-sub">{entry.competency_title}</span>
                    </td>
                    <td className="col-tight cell-patient">{patientOf(entry)}</td>
                    <td className="col-optional">{entry.role_label ?? entry.role}</td>
                    <td>
                      <span className={`pill ${status.className}`}>{status.label}</span>
                    </td>
                    <td className="num col-optional">
                      {formatDate.format(new Date(entry.created_at))}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

export const Logbook = memo(LogbookBase)
