import { useState } from 'react'

const BUCKET_SECONDS = 15
const BUCKET_COUNT = 20 // 5 minutes

const WIDTH = 480
const HEIGHT = 96
const PAD = 8

export function ThroughputSparkline({ buckets }: { buckets: number[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const currentBuckets = buckets.length > 0 ? buckets : new Array(BUCKET_COUNT).fill(0)
  const max = Math.max(1, ...currentBuckets)

  const points = currentBuckets.map((count, i) => {
    const x = PAD + (i / (BUCKET_COUNT - 1)) * (WIDTH - PAD * 2)
    const y = HEIGHT - PAD - (count / max) * (HEIGHT - PAD * 2)
    return { x, y, count }
  })

  const path = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
    .join(' ')

  const total = currentBuckets.reduce((a, b) => a + b, 0)
  const perMinute = ((total / (BUCKET_COUNT * BUCKET_SECONDS)) * 60).toFixed(1)

  return (
    <div
      className="relative"
      aria-label={`Task events over the last 5 minutes, averaging ${perMinute} per minute`}
    >
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full"
        onMouseLeave={() => setHover(null)}
      >
        <line
          x1={PAD}
          y1={HEIGHT - PAD}
          x2={WIDTH - PAD}
          y2={HEIGHT - PAD}
          stroke="var(--color-baseline)"
          strokeWidth={1}
        />
        <path
          d={path}
          fill="none"
          stroke="var(--color-accent)"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {points.map((p, i) => (
          <rect
            key={i}
            x={p.x - (WIDTH / BUCKET_COUNT) / 2}
            y={0}
            width={WIDTH / BUCKET_COUNT}
            height={HEIGHT}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
          />
        ))}
        {hover !== null && (
          <>
            <line
              x1={points[hover].x}
              y1={PAD}
              x2={points[hover].x}
              y2={HEIGHT - PAD}
              stroke="var(--color-gridline)"
              strokeWidth={1}
            />
            <circle
              cx={points[hover].x}
              cy={points[hover].y}
              r={4}
              fill="var(--color-accent)"
              stroke="var(--color-surface)"
              strokeWidth={2}
            />
          </>
        )}
      </svg>
      {hover !== null && (
        <div
          className="pointer-events-none absolute top-0 -translate-x-1/2 -translate-y-full rounded-md border border-border bg-surface px-2 py-1 text-xs text-ink shadow-md"
          style={{ left: `${(points[hover].x / WIDTH) * 100}%` }}
        >
          {points[hover].count} event{points[hover].count === 1 ? '' : 's'}
        </div>
      )}
      <div className="mt-1 flex justify-between text-xs text-ink-muted">
        <span>5 min ago</span>
        <span>now · {perMinute}/min</span>
      </div>
    </div>
  )
}
