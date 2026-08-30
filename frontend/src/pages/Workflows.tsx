import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { listWorkflows } from '../lib/apiClient'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { Spinner } from '../components/Spinner'
import { CreateWorkflowModal } from '../features/workflows/CreateWorkflowModal'
import { WorkflowTable } from '../features/workflows/WorkflowTable'

const PAGE_SIZE = 20

export function Workflows() {
    const [offset, setOffset] = useState(0)
    const [showCreate, setShowCreate] = useState(false)

    const { data: workflows, isLoading, isError } = useQuery({
        queryKey: ['workflows', offset],
        queryFn: () => listWorkflows(PAGE_SIZE, offset),
    })

    return (
        <div className="flex flex-col gap-5">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-lg font-semibold text-ink">Workflows</h1>
                    <p className="text-sm text-ink-muted">
                        Chain tasks together with dependencies. Downstream steps run automatically once their
                        dependencies succeed.
                    </p>
                </div>
                <Button variant="primary" onClick={() => setShowCreate(true)}>
                    New workflow
                </Button>
            </div>

            <div className="flex items-center justify-end gap-2">
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

            <Card>
                {isLoading ? (
                    <div className="flex items-center justify-center py-16">
                        <Spinner />
                    </div>
                ) : isError ? (
                    <div className="px-6 py-16 text-center text-sm text-status-critical">
                        Failed to load workflows.
                    </div>
                ) : (
                    <WorkflowTable workflows={workflows ?? []} />
                )}
            </Card>

            {showCreate && <CreateWorkflowModal onClose={() => setShowCreate(false)} />}
        </div>
    )
}
