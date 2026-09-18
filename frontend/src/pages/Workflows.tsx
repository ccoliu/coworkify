import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError, deleteDefinition, deleteWorkflow, listDefinitions, listWorkflows, rerunWorkflow } from '../lib/apiClient'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { Spinner } from '../components/Spinner'
import { DefinitionTable } from '../features/workflows/DefinitionTable'
import { WorkflowTable } from '../features/workflows/WorkflowTable'
import { useToast } from '../context/ToastContext'

const PAGE_SIZE = 20

export function Workflows() {
    const [offset, setOffset] = useState(0)
    const navigate = useNavigate()
    const queryClient = useQueryClient()
    const { push } = useToast()

    const { data: definitions, isLoading: definitionsLoading, isError: definitionsError } = useQuery({
        queryKey: ['definitions'],
        queryFn: () => listDefinitions(100),
    })

    const { data: workflows, isLoading, isError } = useQuery({
        queryKey: ['workflows', offset],
        queryFn: () => listWorkflows(PAGE_SIZE, offset),
    })

    const rerun = useMutation({
        mutationFn: rerunWorkflow,
        onSuccess: (created) => {
            queryClient.invalidateQueries({ queryKey: ['workflows'] })
            queryClient.invalidateQueries({ queryKey: ['definitions'] })
            push('Re-run started', 'success')
            navigate(`/workflows/${created.id}`)
        },
        onError: (err) => {
            push(err instanceof ApiError ? err.message : 'Failed to re-run workflow', 'error')
        },
    })

    const removeRun = useMutation({
        mutationFn: deleteWorkflow,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['workflows'] })
            queryClient.invalidateQueries({ queryKey: ['definitions'] })
            push('Run deleted', 'success')
        },
        onError: (err) => {
            push(err instanceof ApiError ? err.message : 'Failed to delete run', 'error')
        },
    })

    const removeDefinition = useMutation({
        mutationFn: deleteDefinition,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['definitions'] })
            push('Workflow deleted', 'success')
        },
        onError: (err) => {
            push(err instanceof ApiError ? err.message : 'Failed to delete workflow', 'error')
        },
    })

    return (
        <div className="flex flex-col gap-5">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-lg font-semibold text-ink">Workflows</h1>
                    <p className="text-sm text-ink-muted">
                        Define a pipeline once, then run it with different input. Downstream steps run automatically
                        once their dependencies succeed.{' '}
                        <Link to="/getting-started" className="text-accent hover:underline">
                            第一次使用？看 Getting started
                        </Link>
                    </p>
                </div>
                <Button variant="primary" onClick={() => navigate('/workflows/new')}>
                    New workflow
                </Button>
            </div>

            <Card>
                {definitionsLoading ? (
                    <div className="flex items-center justify-center py-16">
                        <Spinner />
                    </div>
                ) : definitionsError ? (
                    <div className="px-6 py-16 text-center text-sm text-status-critical">Failed to load workflows.</div>
                ) : (
                    <DefinitionTable definitions={definitions ?? []} onDelete={removeDefinition.mutate} />
                )}
            </Card>

            <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-ink">Recent runs</h2>
                <div className="flex items-center gap-2">
                    <Button
                        variant="ghost"
                        disabled={offset === 0}
                        onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
                    >
                        Previous
                    </Button>
                    <Button
                        variant="ghost"
                        disabled={!workflows || workflows.length < PAGE_SIZE}
                        onClick={() => setOffset((o) => o + PAGE_SIZE)}
                    >
                        Next
                    </Button>
                </div>
            </div>

            <Card>
                {isLoading ? (
                    <div className="flex items-center justify-center py-16">
                        <Spinner />
                    </div>
                ) : isError ? (
                    <div className="px-6 py-16 text-center text-sm text-status-critical">Failed to load runs.</div>
                ) : (
                    <WorkflowTable
                        workflows={workflows ?? []}
                        onDelete={removeRun.mutate}
                        onRerun={rerun.mutate}
                        isRerunning={rerun.isPending}
                    />
                )}
            </Card>
        </div>
    )
}
