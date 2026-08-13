import { useEffect, useRef } from 'react'

import { AlertIcon, CheckIcon } from '../../components/icons'
import type { Dashboard as DashboardData } from '../../types'

type CoverageRow = DashboardData['coverage'][number]

/** The full picture for one subject, on demand.
 *
 *  The dashboard panel shows the shape — a grid of squares and the ratio. The
 *  names belong here: two logged competencies were tolerable inline, but a real
 *  curriculum has forty, and the useful half is the part with no evidence yet,
 *  which could never have sat on the dashboard at all.
 */
export function CoverageDialog({ row, onClose }: { row: CoverageRow; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    // The page behind must not scroll while the dialog owns the screen.
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
    }
  }, [onClose])

  const logged = row.competencies.filter((c) => !c.retired)
  const retired = row.competencies.filter((c) => c.retired)

  return (
    <div
      className="dialog-scrim"
      role="presentation"
      onClick={(event) => event.target === event.currentTarget && onClose()}
    >
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="coverage-dialog-title"
      >
        <header className="dialog-head">
          <div>
            <span className="eyebrow">Coverage</span>
            <h2 id="coverage-dialog-title">{row.subject}</h2>
            <p>
              {row.total === 0
                ? 'No competencies set up for this speciality yet.'
                : `${row.covered} of ${row.total} competencies have evidence`}
            </p>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="btn btn-quiet"
            onClick={onClose}
            aria-label="Close"
          >
            Close
          </button>
        </header>

        <div className="dialog-body">
          {logged.length > 0 && (
            <section className="dialog-group">
              <h3>
                <span className="dialog-mark is-ok" aria-hidden>
                  <CheckIcon width={12} height={12} />
                </span>
                Logged · {logged.length}
              </h3>
              <ul className="dialog-list">
                {logged.map((item) => (
                  <li key={item.id}>
                    <em>{item.logged}</em>
                    <span>{item.title}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {retired.length > 0 && (
            <section className="dialog-group">
              <h3>Removed from the catalogue · {retired.length}</h3>
              <p className="dialog-note">
                These cases still happened, but the competency is no longer in the curriculum,
                so they sit outside the ratio above.
              </p>
              <ul className="dialog-list is-retired">
                {retired.map((item) => (
                  <li key={item.id}>
                    <em>{item.logged}</em>
                    <span>{item.title}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {row.gaps.length > 0 && (
            <section className="dialog-group">
              <h3>
                <span className="dialog-mark is-gap" aria-hidden>
                  <AlertIcon width={12} height={12} />
                </span>
                No evidence yet · {row.gaps.length}
              </h3>
              <ul className="dialog-list is-gaps">
                {row.gaps.map((item) => (
                  <li key={item.id}>
                    <span>{item.title}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {logged.length === 0 && row.gaps.length === 0 && (
            <p className="dialog-note">
              This speciality has no competencies set up. Load its curriculum in Configuration.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
