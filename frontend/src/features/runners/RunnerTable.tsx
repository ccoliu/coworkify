import { useMutation, useQueryClient } from '@tanstack/react-query'
import { formatRelativeTime, shortId } from '../../lib/format'
import type { Runner } from '../../lib/types'
import { ApiError, deleteRunner } from '../../lib/apiClient'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { useToast } from '../../context/ToastContext'

export function RunnerTable({ runners }: { runners: Runner[] }) {
    const queryClient = useQueryClient()
    const { push } = useToast()

    const deleteMutation = useMutation({
        mutationFn: deleteRunner,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['runners'] })
            push('Runner deleted', 'success')
        },
        onError: (err) => push(err instanceof ApiError ? err.message : 'Failed to delete runner', 'error'),
    })

    if (runners.length === 0) {
        return (
            <EmptyState
                title="No runners yet"
                description="Create a runner and point a task or workflow step's runner_id at it to have it execute on your own machine instead of the shared workers."
            />
        )
    }

    return (
        <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
                <thead>
                    <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-ink-muted">
                        <th className="px-4 py-2.5 font-medium">Name</th>
                        <th className="px-4 py-2.5 font-medium">Runner ID</th>
                        <th className="px-4 py-2.5 font-medium">Last seen</th>
                        <th className="px-4 py-2.5 font-medium" />
                    </tr>
                </thead>
                <tbody>
                    {runners.map((runner) => (
                        <tr key={runner.id} className="border-b border-border last:border-0 hover:bg-surface">
                            <td className="px-4 py-3 font-medium text-ink">{runner.name}</td>
                            <td className="px-4 py-3 font-mono text-xs text-ink-muted">{shortId(runner.id)}</td>
                            <td className="px-4 py-3 text-ink-muted">
                                {runner.last_seen_at ? formatRelativeTime(runner.last_seen_at) : 'Never'}
                            </td>
                            <td className="px-4 py-3 text-right">
                                <Button
                                    variant="ghost"
                                    className="text-status-critical hover:text-status-critical"
                                    onClick={() => {
                                        if (confirm(`Delete runner "${runner.name}"?`)) {
                                            deleteMutation.mutate(runner.id)
                                        }
                                    }}
                                >
                                    Delete
                                </Button>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    )
}
