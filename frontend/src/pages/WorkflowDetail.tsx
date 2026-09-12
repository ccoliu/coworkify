import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError, deleteWorkflow, getWorkflow } from '../lib/apiClient'
import { formatDateTime } from '../lib/format'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { EmptyState } from '../components/EmptyState'
import { Spinner } from '../components/Spinner'
import { StatusBadge } from '../components/StatusBadge'
import { PromoteToScheduleModal } from '../features/workflows/PromoteToScheduleModal'
import { StepDetailPanel } from '../features/workflows/StepDetailPanel'
import { WorkflowCanvas } from '../features/workflows/WorkflowCanvas'
import { useToast } from '../context/ToastContext'
import { useWs } from '../context/WsContext'
import { useWideLayout } from '../context/LayoutContext'

export function WorkflowDetail() {
    const { id } = useParams<{ id: string }>()
    const [showScheduleModal, setShowScheduleModal] = useState(false)
    const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
    const queryClient = useQueryClient()
    const navigate = useNavigate()
    const { push } = useToast()
    const { events, status: wsStatus } = useWs()

    const remove = useMutation({
        mutationFn: deleteWorkflow,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['workflows'] })
            push('Workflow deleted', 'success')
            navigate('/workflows')
        },
        onError: (err) => {
            push(err instanceof ApiError ? err.message : 'Failed to delete workflow', 'error')
        },
    })

    const {
        data: workflow,
        isLoading,
        isError,
    } = useQuery({
        queryKey: ['workflow', id],
        queryFn: () => getWorkflow(id as string),
        enabled: !!id,
        // WS 推的是 task 事件，workflow 本身的 status 是 worker 在最後一個 task 收尾時
        // 才寫進 DB 的，可能比事件晚一點到，所以執行中仍留一個慢速輪詢當保險。
        refetchInterval: (query) => {
            if (query.state.data?.status !== 'pending') return false
            return wsStatus === 'open' ? 5000 : 1500
        },
    })

    // 這個 workflow 底下任何 task 有狀態變化就重抓一次，省掉 1.5 秒輪詢。
    // 用 join 出來的字串當相依值（而不是 workflow 物件），避免「重抓 → 新物件 →
    // 再重抓」的無窮迴圈。
    const stepTaskIds = workflow?.steps.map((s) => s.task_id).join(',') ?? ''
    useEffect(() => {
        if (!id || events.length === 0 || !stepTaskIds) return
        const ids = new Set(stepTaskIds.split(','))
        if (!events.some((e) => ids.has(e.task_id))) return
        queryClient.invalidateQueries({ queryKey: ['workflow', id] })
    }, [events, stepTaskIds, id, queryClient])

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

    const selectedStep = workflow.steps.find((s) => s.task_id === selectedTaskId) ?? null

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
                <Button
                    variant="danger"
                    onClick={() => {
                        if (confirm(`Delete workflow "${workflow.name}"?`)) remove.mutate(workflow.id)
                    }}
                >
                    Delete
                </Button>
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

            <Card className="overflow-hidden p-0">
                <div className="flex flex-col lg:h-[min(78vh,900px)] lg:flex-row">
                    <div className="h-[380px] min-w-0 flex-1 lg:h-auto">
                        <WorkflowCanvas
                            steps={workflow.steps}
                            selectedTaskId={selectedTaskId}
                            onSelect={setSelectedTaskId}
                        />
                    </div>
                    {selectedStep && (
                        <StepDetailPanel step={selectedStep} onClose={() => setSelectedTaskId(null)} />
                    )}
                </div>
            </Card>
        </div>
    )
}
