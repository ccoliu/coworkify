import { useQueries } from '@tanstack/react-query'
import { listTasks } from '../../lib/apiClient'
import { TASK_STATUSES, type TaskStatus } from '../../lib/types'

const COUNT_CAP = 100

export interface StatusCount {
  status: TaskStatus
  count: number
  capped: boolean
}

export function useStatusCounts() {
  const results = useQueries({
    queries: TASK_STATUSES.map((status) => ({
      queryKey: ['tasks', 'count', status],
      queryFn: () => listTasks({ status, limit: COUNT_CAP, offset: 0 }),
      refetchInterval: 10000,
    })),
  })

  const isLoading = results.some((r) => r.isLoading)
  const counts: StatusCount[] = TASK_STATUSES.map((status, i) => ({
    status,
    count: results[i].data?.length ?? 0,
    capped: (results[i].data?.length ?? 0) >= COUNT_CAP,
  }))

  return { counts, isLoading }
}
