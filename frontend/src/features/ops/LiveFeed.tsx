import { Link } from 'react-router-dom'
import { shortId } from '../../lib/format'
import type { WsTaskUpdate } from '../../lib/types'
import { EmptyState } from '../../components/EmptyState'
import { StatusBadge } from '../../components/StatusBadge'

export function LiveFeed({ events }: { events: WsTaskUpdate[] }) {
  if (events.length === 0) {
    return (
      <EmptyState
        title="No live events yet"
        description="Status updates will appear here as tasks run."
      />
    )
  }

  return (
    <ul className="flex max-h-96 flex-col divide-y divide-border overflow-y-auto">
      {events.slice(0, 50).map((event, i) => (
        <li key={i} className="flex items-center justify-between gap-3 py-2.5 text-sm">
          <div className="flex items-center gap-3">
            <StatusBadge status={event.status} />
            <Link
              to={`/tasks/${event.task_id}`}
              className="font-mono text-xs text-ink-secondary hover:text-accent"
            >
              {shortId(event.task_id)}
            </Link>
          </div>
          <span className="text-xs text-ink-muted">
            {new Date(event.timestamp * 1000).toLocaleTimeString()}
          </span>
        </li>
      ))}
    </ul>
  )
}
