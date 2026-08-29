import { useQueryClient } from '@tanstack/react-query'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import type { WsTaskUpdate } from '../lib/types'

export type WsStatus = 'connecting' | 'open' | 'closed'

const MAX_LIVE_EVENTS = 100
const BUCKET_SECONDS = 15
const BUCKET_COUNT = 20 // 5 minutes = 300 seconds

export interface WsContextValue {
  status: WsStatus
  events: WsTaskUpdate[]
  throughputBuckets: number[]
  errorRate: string | null
}

const WsContext = createContext<WsContextValue>({
  status: 'closed',
  events: [],
  throughputBuckets: new Array(BUCKET_COUNT).fill(0),
  errorRate: null,
})

function buildWsUrl(): string {
  const configured = import.meta.env.VITE_WS_URL
  if (configured) return configured
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/tasks`
}

export function WsProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<WsStatus>('connecting')
  const [events, setEvents] = useState<WsTaskUpdate[]>([])
  const [throughputBuckets, setThroughputBuckets] = useState<number[]>(() =>
    new Array(BUCKET_COUNT).fill(0)
  )
  const [errorRate, setErrorRate] = useState<string | null>(null)

  const queryClient = useQueryClient()
  const reconnectDelay = useRef(1000)

  // Map from bucketKey (floor(timestamp / 15)) -> { total: number, failed: number }
  const bucketMapRef = useRef<Map<number, { total: number; failed: number }>>(new Map())
  const incomingEventsRef = useRef<WsTaskUpdate[]>([])
  const flushTimerRef = useRef<number | null>(null)

  const computeMetrics = useCallback(() => {
    const nowSec = Date.now() / 1000
    const currentKey = Math.floor(nowSec / BUCKET_SECONDS)
    const oldestKey = currentKey - (BUCKET_COUNT - 1)

    // Clean up old keys
    for (const key of bucketMapRef.current.keys()) {
      if (key < oldestKey - 5) {
        bucketMapRef.current.delete(key)
      }
    }

    const buckets = new Array(BUCKET_COUNT).fill(0)
    let totalEvents = 0
    let failedEvents = 0

    for (let i = 0; i < BUCKET_COUNT; i++) {
      const key = oldestKey + i
      const data = bucketMapRef.current.get(key)
      if (data) {
        buckets[i] = data.total
        totalEvents += data.total
        failedEvents += data.failed
      }
    }

    setThroughputBuckets(buckets)
    setErrorRate(
      totalEvents === 0 ? null : ((failedEvents / totalEvents) * 100).toFixed(0)
    )
  }, [])

  useEffect(() => {
    let socket: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let cancelled = false

    // Tick every second to slide time window forward smoothly
    const interval = setInterval(() => {
      computeMetrics()
    }, 1000)

    function flushUpdates() {
      if (incomingEventsRef.current.length === 0) return
      const batch = incomingEventsRef.current
      incomingEventsRef.current = []

      setEvents((prev) => {
        const next = [...batch, ...prev]
        return next.length > MAX_LIVE_EVENTS ? next.slice(0, MAX_LIVE_EVENTS) : next
      })

      // Invalidate queries throttled per batch
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      computeMetrics()
    }

    function scheduleFlush() {
      if (flushTimerRef.current === null) {
        flushTimerRef.current = window.setTimeout(() => {
          flushTimerRef.current = null
          flushUpdates()
        }, 80)
      }
    }

    function connect() {
      setStatus('connecting')
      socket = new WebSocket(buildWsUrl())

      socket.onopen = () => {
        reconnectDelay.current = 1000
        setStatus('open')
      }

      socket.onmessage = (event) => {
        try {
          const update = JSON.parse(event.data) as WsTaskUpdate
          const ts = typeof update.timestamp === 'number' ? update.timestamp : Date.now() / 1000
          const key = Math.floor(ts / BUCKET_SECONDS)

          const entry = bucketMapRef.current.get(key) || { total: 0, failed: 0 }
          entry.total++
          if (update.status === 'failed') {
            entry.failed++
          }
          bucketMapRef.current.set(key, entry)

          incomingEventsRef.current.unshift(update)
          scheduleFlush()
        } catch {
          // ignore malformed frames
        }
      }

      socket.onclose = () => {
        if (cancelled) return
        setStatus('closed')
        reconnectTimer = setTimeout(connect, reconnectDelay.current)
        reconnectDelay.current = Math.min(reconnectDelay.current * 2, 15000)
      }

      socket.onerror = () => {
        socket?.close()
      }
    }

    connect()

    return () => {
      cancelled = true
      clearInterval(interval)
      if (flushTimerRef.current !== null) {
        clearTimeout(flushTimerRef.current)
      }
      if (reconnectTimer) clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [computeMetrics, queryClient])

  return (
    <WsContext.Provider value={{ status, events, throughputBuckets, errorRate }}>
      {children}
    </WsContext.Provider>
  )
}

export function useWs() {
  return useContext(WsContext)
}
