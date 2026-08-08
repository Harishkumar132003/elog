import { memo } from 'react'

interface Props {
  title: string
  body: string
  action?: { label: string; onClick: () => void }
}

function EmptyStateBase({ title, body, action }: Props) {
  return (
    <div className="empty card">
      <span className="empty-mark" aria-hidden />
      <h2>{title}</h2>
      <p>{body}</p>
      {action && (
        <button type="button" className="btn btn-primary" onClick={action.onClick}>
          {action.label}
        </button>
      )}
    </div>
  )
}

export const EmptyState = memo(EmptyStateBase)
