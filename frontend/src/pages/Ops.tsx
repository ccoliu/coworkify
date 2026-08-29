import { Card } from '../components/Card'
import { useWs } from '../context/WsContext'
import { LiveFeed } from '../features/ops/LiveFeed'
import { StatTile } from '../features/ops/StatTile'
import { ThroughputSparkline } from '../features/ops/ThroughputSparkline'
import { useStatusCounts } from '../features/ops/useStatusCounts'

export function Ops() {
  const { counts } = useStatusCounts()
  const { events, throughputBuckets, errorRate } = useWs()

  const byStatus = Object.fromEntries(counts.map((c) => [c.status, c])) as Record<
    string,
    (typeof counts)[number]
  >
  const queueDepth = (byStatus.pending?.count ?? 0) + (byStatus.running?.count ?? 0)

  function display(c: (typeof counts)[number] | undefined) {
    if (!c) return '—'
    return c.capped ? `${c.count}+` : c.count
  }

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-lg font-semibold text-ink">Ops</h1>
        <p className="text-sm text-ink-muted">
          Live snapshot of queue depth and throughput. Status counts refresh every 10s.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <StatTile label="Pending" value={display(byStatus.pending)} />
        <StatTile label="Running" value={display(byStatus.running)} tone="default" />
        <StatTile label="Retrying" value={display(byStatus.retrying)} tone="warning" />
        <StatTile label="Success" value={display(byStatus.success)} tone="good" />
        <StatTile label="Failed" value={display(byStatus.failed)} tone="critical" />
        <StatTile label="Queue depth" value={queueDepth} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="p-5 lg:col-span-2">
          <h2 className="mb-3 text-sm font-semibold text-ink">Throughput</h2>
          <ThroughputSparkline buckets={throughputBuckets} />
        </Card>
        <StatTile
          label="Error rate (5 min)"
          value={errorRate === null ? 'no data' : `${errorRate}%`}
          tone={errorRate !== null && Number(errorRate) > 0 ? 'critical' : 'default'}
        />
      </div>

      <Card className="p-5">
        <h2 className="mb-3 text-sm font-semibold text-ink">Live activity</h2>
        <LiveFeed events={events} />
      </Card>
    </div>
  )
}
