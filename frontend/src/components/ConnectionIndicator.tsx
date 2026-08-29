import { useWs } from '../context/WsContext'

const LABEL: Record<string, string> = {
  open: 'Live',
  connecting: 'Connecting…',
  closed: 'Disconnected',
}

const DOT: Record<string, string> = {
  open: 'bg-status-good',
  connecting: 'bg-status-warning animate-pulse',
  closed: 'bg-status-critical',
}

export function ConnectionIndicator() {
  const { status } = useWs()
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-ink-secondary">
      <span className={`h-1.5 w-1.5 rounded-full ${DOT[status]}`} />
      {LABEL[status]}
    </span>
  )
}
