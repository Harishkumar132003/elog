import { useEffect, useRef, type ReactNode } from 'react'

interface Props {
  title: string
  /** One line under the title: what is about to happen, plainly. */
  lede?: string
  /** The consequences, one per line. Shown as a list, not a paragraph. */
  points?: ReactNode[]
  confirmLabel: string
  cancelLabel?: string
  /** Destructive actions get a red confirm, so the button itself carries the
   *  warning rather than relying on the text being read. */
  danger?: boolean
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}

/** A last gate before something irreversible.
 *
 *  Focus lands on Cancel for a destructive action and on Confirm otherwise —
 *  the default should be the safe one when the outcome cannot be undone.
 */
export function ConfirmDialog({
  title,
  lede,
  points,
  confirmLabel,
  cancelLabel = 'Cancel',
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}: Props) {
  const focusRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    focusRef.current?.focus()
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onCancel()
    document.addEventListener('keydown', onKey)
    // The page behind must not scroll while the dialog owns the screen.
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
    }
  }, [onCancel])

  return (
    <div
      className="confirm-scrim"
      role="presentation"
      onClick={(event) => event.target === event.currentTarget && onCancel()}
    >
      <div className="confirm" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
        <h2 id="confirm-title">{title}</h2>
        {lede && <p className="confirm-lede">{lede}</p>}

        {points && points.length > 0 && (
          <ul className="confirm-points">
            {points.map((point, index) => (
              <li key={index}>{point}</li>
            ))}
          </ul>
        )}

        <div className="confirm-actions">
          <button
            type="button"
            className="btn btn-quiet"
            disabled={busy}
            ref={danger ? focusRef : undefined}
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`}
            disabled={busy}
            ref={danger ? undefined : focusRef}
            onClick={onConfirm}
          >
            {busy ? 'Working…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
