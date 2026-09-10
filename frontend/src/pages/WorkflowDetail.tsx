import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getWorkflow } from '../lib/apiClient'
import { formatDateTime, shortId } from '../lib/format'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { EmptyState } from '../components/EmptyState'
import { Spinner } from '../components/Spinner'
import { StatusBadge } from '../components/StatusBadge'
import { computeLevels } from '../features/workflows/dagLayout'
import { PromoteToScheduleModal } from '../features/workflows/PromoteToScheduleModal'

export function WorkflowDetail() {
    const { id } = useParams<{ id: string }>()
    const [showScheduleModal, setShowScheduleModal] = useState(false)

    const {
        data: workflow,
        isLoading,
        isError,
    } = useQuery({
        queryKey: ['workflow', id],
        queryFn: () => getWorkflow(id as string),
        enabled: !!id,
        refetchInterval: (query) => (query.state.data?.status === 'pending' ? 1500 : false),
    })

    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-16">
                <Spinner />
            </div>
        )
    }

    if (isError || !workflow) {
        return (
            <EmptyState
                title="Workflow not found"
                action={
                    <Link to="/workflows" className="text-sm font-medium text-accent">
                        Back to workflows
                    </Link>
                }
            />
        )
    }

    const byTaskId = new Map(workflow.steps.map((s) => [s.task_id, s]))
    const levels = computeLevels(workflow.steps)

    return (
        <div className="flex flex-col gap-5">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <Link to="/workflows" className="text-sm text-ink-muted hover:text-ink">
                        ← Workflows
                    </Link>
                    <div className="mt-1 flex items-center gap-3">
                        <h1 className="text-lg font-semibold text-ink">{workflow.name}</h1>
                        <StatusBadge status={workflow.status} />
                    </div>
                    <div className="mt-1 font-mono text-xs text-ink-muted">{workflow.id}</div>
                </div>
                {workflow.steps_template && (
                    <Button variant="secondary" onClick={() => setShowScheduleModal(true)}>
                        Schedule this workflow
                    </Button>
                )}
            </div>

            {showScheduleModal && (
                <PromoteToScheduleModal
                    workflowId={workflow.id}
                    workflowName={workflow.name}
                    onClose={() => setShowScheduleModal(false)}
                />
            )}

            <Card className="p-5">
                <dl className="grid grid-cols-2 gap-5 sm:grid-cols-4">
                    <div>
                        <dt className="text-xs uppercase tracking-wide text-ink-muted">Steps</dt>
                        <dd className="mt-0.5 text-sm text-ink">{workflow.steps.length}</dd>
                    </div>
                    <div>
                        <dt className="text-xs uppercase tracking-wide text-ink-muted">Created</dt>
                        <dd className="mt-0.5 text-sm text-ink">{formatDateTime(workflow.created_at)}</dd>
                    </div>
                    <div>
                        <dt className="text-xs uppercase tracking-wide text-ink-muted">Updated</dt>
                        <dd className="mt-0.5 text-sm text-ink">{formatDateTime(workflow.updated_at)}</dd>
                    </div>
                </dl>
            </Card>

            <Card className="overflow-x-auto p-5">
                <h2 className="mb-4 text-sm font-semibold text-ink">Pipeline</h2>
                <div className="flex items-start gap-6">
                    {levels.map((level, i) => (
                        <div key={i} className="flex items-center gap-6">
                            <div className="flex flex-col gap-3">
                                {level.map((step) => (
                                    <div key={step.id} className="w-56 rounded-lg border border-border bg-plane p-3">
                                        <span className="truncate text-sm font-medium text-ink">
                                            {step.task_name ?? shortId(step.task_id)}
                                        </span>
                                        <div className="mt-1 flex items-center justify-between">
                                            <span className="font-mono text-xs text-ink-muted">{step.task_type}</span>
                                            <StatusBadge status={step.task_status ?? 'pending'} />
                                        </div>
                                        {step.depends_on.length > 0 && (
                                            <div className="mt-2 text-xs text-ink-muted">
                                                depends on:{' '}
                                                {step.depends_on
                                                    .map((depId) => byTaskId.get(depId)?.task_name ?? shortId(depId))
                                                    .join(', ')}
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                            {i < levels.length - 1 && <span className="text-lg text-ink-muted">→</span>}
                        </div>
                    ))}
                </div>
            </Card>
        </div>
    )
}
