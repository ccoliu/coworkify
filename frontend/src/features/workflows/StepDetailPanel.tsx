import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { StatusBadge } from '../../components/StatusBadge'
import { Spinner } from '../../components/Spinner'
import { getTask } from '../../lib/apiClient'
import { formatDateTime } from '../../lib/format'
import type { WorkflowStep } from '../../lib/types'
import { JsonBlock } from '../../components/JsonBlock'
import { TaskLogList } from '../tasks/TaskLogList'

function Row({ label, value }: { label: string; value: React.ReactNode }) {
    return (
        <div className="flex items-baseline justify-between gap-3 py-1">
            <span className="shrink-0 text-xs uppercase tracking-wide text-ink-muted">{label}</span>
            <span className="min-w-0 truncate text-right text-sm text-ink">{value}</span>
        </div>
    )
}

export function StepDetailPanel({ step, onClose }: { step: WorkflowStep; onClose: () => void }) {
    const { data: task, isLoading, isError } = useQuery({
        queryKey: ['task', step.task_id],
        queryFn: () => getTask(step.task_id),
    })

    return (
        <aside className="flex w-full shrink-0 flex-col border-t border-border bg-surface lg:w-80 lg:border-l lg:border-t-0">
            <div className="flex items-start justify-between gap-2 border-b border-border px-3 py-2.5">
                <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-ink">{step.task_name ?? 'Step'}</p>
                    <p className="font-mono text-xs text-ink-muted">{step.task_type}</p>
                </div>
                <button
                    type="button"
                    onClick={onClose}
                    className="shrink-0 text-sm text-ink-muted hover:text-ink"
                    aria-label="Clear selection"
                >
                    ✕
                </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
                <Row label="Status" value={<StatusBadge status={step.task_status ?? 'pending'} />} />
                {step.branch_of_key && <Row label="Branch" value={`when ${step.branch_when}`} />}

                {isLoading && (
                    <div className="flex justify-center py-6">
                        <Spinner />
                    </div>
                )}
                {isError && <p className="py-3 text-sm text-ink-muted">This task is no longer available.</p>}

                {task && (
                    <>
                        <Row label="Priority" value={task.priority} />
                        <Row label="Retries" value={`${task.retry_count} / ${task.max_retries}`} />
                        <Row label="Updated" value={formatDateTime(task.updated_at)} />
                        <div className="mt-2">
                            <p className="mb-1 text-xs uppercase tracking-wide text-ink-muted">Payload</p>
                            <JsonBlock value={task.payload} className="max-h-60 p-2" />
                        </div>

                        <div className="mt-3">
                            <p className="mb-1.5 text-xs uppercase tracking-wide text-ink-muted">
                                Execution history
                            </p>
                            <TaskLogList taskId={step.task_id} compact />
                        </div>
                    </>
                )}
            </div>

            <div className="border-t border-border px-3 py-2">
                <Link to={`/tasks/${step.task_id}`} className="text-sm font-medium text-accent">
                    Open task detail →
                </Link>
            </div>
        </aside>
    )
}
