import type { TaskStatus } from '../lib/types'

const STYLES: Record<TaskStatus, { dot: string; text: string; label: string }> = {
  pending: { dot: 'bg-ink-muted', text: 'text-ink-secondary', label: 'Pending' },
  running: { dot: 'bg-accent animate-pulse', text: 'text-accent', label: 'Running' },
  retrying: { dot: 'bg-status-warning', text: 'text-status-warning', label: 'Retrying' },
  success: { dot: 'bg-status-good', text: 'text-status-good', label: 'Success' },
  failed: { dot: 'bg-status-critical', text: 'text-status-critical', label: 'Failed' },
  cancelled: { dot: 'bg-ink-muted', text: 'text-ink-muted', label: 'Cancelled' },
}

export function StatusBadge({ status }: { status: TaskStatus }) {
  const style = STYLES[status] ?? STYLES.pending
  return (
    <span className={`inline-flex items-center gap-1.5 text-sm font-medium ${style.text}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
      {style.label}
    </span>
  )
}
