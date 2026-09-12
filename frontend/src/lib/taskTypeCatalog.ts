import { useQuery } from '@tanstack/react-query'
import { listTaskTypes } from './apiClient'
import type { TaskTypeSpec } from './types'

export function useTaskTypeCatalog() {
  return useQuery({
    queryKey: ['task-types'],
    queryFn: listTaskTypes,
    staleTime: Infinity, // 任務類型清單是後端程式碼定義的，執行期間不會變
  })
}

export function defaultPayloadFor(spec: TaskTypeSpec | undefined): Record<string, unknown> {
  if (!spec) return {}
  return Object.fromEntries(spec.fields.map((f) => [f.key, f.default]))
}
