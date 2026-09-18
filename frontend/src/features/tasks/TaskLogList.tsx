import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { listTaskLogs } from '../../lib/apiClient'
import { formatDateTime } from '../../lib/format'
import { JsonBlock } from '../../components/JsonBlock'
import { Spinner } from '../../components/Spinner'
import { StatusBadge } from '../../components/StatusBadge'
import { useWs } from '../../context/WsContext'

/**
 * 一個 task 的完整執行歷程（GET /tasks/{id}/logs）。
 * WebSocket 只推當下這一輪，所以這裡以 DB 為準，收到該 task 的事件時再重抓。
 */
export function useTaskLogs(taskId: string | undefined) {
    const queryClient = useQueryClient()
    const { events } = useWs()

    const query = useQuery({
        queryKey: ['task-logs', taskId],
        queryFn: () => listTaskLogs(taskId as string),
        enabled: !!taskId,
    })

    // 事件本身不含 log id，所以看「這個 task 的事件數量」有沒有變就夠了
    const eventCount = events.filter((e) => e.task_id === taskId).length
    useEffect(() => {
        if (!taskId || eventCount === 0) return
        queryClient.invalidateQueries({ queryKey: ['task-logs', taskId] })
    }, [eventCount, taskId, queryClient])

    return query
}

export function TaskLogList({ taskId, compact = false }: { taskId: string, compact?: boolean }) {
    const { data: logs, isLoading, isError } = useTaskLogs(taskId)

    if (isLoading) {
        return (
            <div className="flex justify-center py-6">
                <Spinner />
            </div>
        )
    }

    if (isError) return <p className="text-sm text-status-critical">Failed to load execution history.</p>
    if (!logs || logs.length === 0) {
        return <p className="text-sm text-ink-muted">還沒有執行紀錄——這個步驟尚未開始，或正在等待上游。</p>
    }

    return (
        <ol className="flex flex-col gap-3">
            {logs.map((log, i) => (
                <li key={log.id} className="flex items-start gap-3 text-sm">
                    <span className="w-5 shrink-0 pt-0.5 text-right font-mono text-xs text-ink-muted">{i + 1}</span>
                    <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                            <StatusBadge status={log.status} />
                            <span className="text-xs text-ink-muted">{formatDateTime(log.created_at)}</span>
                            {log.execution_time_ms != null && (
                                <span className="text-xs text-ink-muted">{Math.round(log.execution_time_ms)} ms</span>
                            )}
                        </div>
                        {log.error_message && (
                            <p className="mt-1 whitespace-pre-wrap break-words text-xs text-status-critical">
                                {log.error_message}
                            </p>
                        )}
                        {log.result != null && (
                            <JsonBlock value={log.result} className={compact ? 'max-h-40 p-2' : ''} />
                        )}
                    </div>
                </li>
            ))}
        </ol>
    )
}

