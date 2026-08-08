import { memo, useMemo } from 'react'

import type { AuthUser, Entry } from '../../types'
import { EmptyState } from './EmptyState'

interface Props {
  residents: readonly AuthUser[]
  entries: readonly Entry[]
  loading: boolean
}

function ResidentsBase({ residents, entries, loading }: Props) {
  // Per-resident case counts and how far each case got through the loop.
  const summary = useMemo(() => {
    const rows = new Map<string, { cases: number; awaiting: number; reasoned: number }>()
    for (const entry of entries) {
      const row = rows.get(entry.resident_id) ?? { cases: 0, awaiting: 0, reasoned: 0 }
      row.cases += 1
      if (entry.status === 'logged') row.awaiting += 1
      if (entry.status === 'answered') row.reasoned += 1
      rows.set(entry.resident_id, row)
    }
    return rows
  }, [entries])

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Supervision</span>
          <h1 className="page-title">My residents</h1>
        </div>
        <p className="page-sub">
          Coverage is what examiners read. An unlogged competency is a visible gap.
        </p>
      </div>

      {!loading && residents.length === 0 ? (
        <EmptyState title="No residents assigned" body="Residents linked to you appear here." />
      ) : (
        <div className="card table-card">
          <table className="table">
            <thead>
              <tr>
                <th>Resident</th>
                <th>Year</th>
                <th>Department</th>
                <th className="num">Cases</th>
                <th className="num">To certify</th>
                <th className="num">Reasoned</th>
              </tr>
            </thead>
            <tbody>
              {residents.map((resident) => {
                const row = summary.get(resident.id)
                return (
                  <tr key={resident.id}>
                    <td className="strong">{resident.name}</td>
                    <td>{resident.year ?? '—'}</td>
                    <td>{resident.department ?? '—'}</td>
                    <td className="num">{row?.cases ?? 0}</td>
                    <td className="num">
                      {row?.awaiting ? (
                        <span className="pill pill-warm">{row.awaiting}</span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="num">{row?.reasoned ?? 0}</td>
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

export const Residents = memo(ResidentsBase)
