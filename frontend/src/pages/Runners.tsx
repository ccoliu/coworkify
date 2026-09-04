import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { listRunners } from '../lib/apiClient'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { Spinner } from '../components/Spinner'
import { CreateRunnerModal } from '../features/runners/CreateRunnerModal'
import { RunnerTable } from '../features/runners/RunnerTable'

export function Runners() {
    const [showCreate, setShowCreate] = useState(false)

    const { data: runners, isLoading, isError } = useQuery({
        queryKey: ['runners'],
        queryFn: listRunners,
    })

    return (
        <div className="flex flex-col gap-5">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-lg font-semibold text-ink">Runners</h1>
                    <p className="text-sm text-ink-muted">
                        Local agents that run tasks on your own machine instead of the shared workers. See{' '}
                        <code className="font-mono">runner/README.md</code> for setup.
                    </p>
                </div>
                <Button variant="primary" onClick={() => setShowCreate(true)}>
                    New runner
                </Button>
            </div>

            <Card>
                {isLoading ? (
                    <div className="flex items-center justify-center py-16">
                        <Spinner />
                    </div>
                ) : isError ? (
                    <div className="px-6 py-16 text-center text-sm text-status-critical">
                        Failed to load runners.
                    </div>
                ) : (
                    <RunnerTable runners={runners ?? []} />
                )}
            </Card>

            {showCreate && <CreateRunnerModal onClose={() => setShowCreate(false)} />}
        </div>
    )
}
