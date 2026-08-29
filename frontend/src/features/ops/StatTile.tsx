import clsx from 'clsx'
import type { ReactNode } from 'react'
import { Card } from '../../components/Card'

export function StatTile({
  label,
  value,
  tone = 'default',
}: {
  label: string
  value: ReactNode
  tone?: 'default' | 'good' | 'warning' | 'critical'
}) {
  const toneClass = {
    default: 'text-ink',
    good: 'text-status-good',
    warning: 'text-status-warning',
    critical: 'text-status-critical',
  }[tone]

  return (
    <Card className="p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
        {label}
      </p>
      <p className={clsx('mt-1.5 text-2xl font-semibold tabular-nums', toneClass)}>
        {value}
      </p>
    </Card>
  )
}
