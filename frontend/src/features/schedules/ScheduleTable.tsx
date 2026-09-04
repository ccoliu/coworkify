import { useMutation, useQueryClient } from '@tanstack/react-query'
import { formatDateTime, formatRelativeTime, shortId } from '../../lib/format'
import type { WorkflowSchedule } from '../../lib/types'
import { ApiError, deleteSchedule, updateSchedule } from '../../lib/apiClient'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { useToast } from '../../context/ToastContext'
import { useState } from 'react'
import { EditScheduleModal } from './EditScheduleModal'

export function ScheduleTable({ schedules }: { schedules: WorkflowSchedule[] }) {
    const queryClient = useQueryClient()
    const { push } = useToast()
    const [editing, setEditing] = useState<WorkflowSchedule | null>(null)

    const toggleMutation = useMutation({
        mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => updateSchedule(id, { enabled }),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['schedules'] }),
        onError: (err) => push(err instanceof ApiError ? err.message : 'Failed to update schedule', 'error'),
    })

    const deleteMutation = useMutation({
        mutationFn: deleteSchedule,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['schedules'] })
            push('Schedule deleted', 'success')
        },
        onError: (err) => push(err instanceof ApiError ? err.message : 'Failed to delete schedule', 'error'),
    })

    if (schedules.length === 0) {
        return (
            <EmptyState
                title="No schedules yet"
                description="Create a schedule to run a workflow automatically on a recurring basis."
            />
        )
    }

    return (
        <>
            <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                    <thead>
                        <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-ink-muted">
                            <th className="px-4 py-2.5 font-medium">Name</th>
                            <th className="px-4 py-2.5 font-medium">Cron</th>
                            <th className="px-4 py-2.5 font-medium">Steps</th>
                            <th className="px-4 py-2.5 font-medium">Next run</th>
                            <th className="px-4 py-2.5 font-medium">Last run</th>
                            <th className="px-4 py-2.5 font-medium">Enabled</th>
                            <th className="px-4 py-2.5 font-medium" />
                        </tr>
                    </thead>
                    <tbody>
                        {schedules.map((sched) => (
                            <tr key={sched.id} className="border-b border-border last:border-0 hover:bg-surface">
                                <td className="px-4 py-3">
                                    <div className="font-medium text-ink">{sched.name}</div>
                                    <div className="font-mono text-xs text-ink-muted">{shortId(sched.id)}</div>
                                </td>
                                <td className="px-4 py-3 font-mono text-xs text-ink-secondary">{sched.cron_expression}</td>
                                <td className="px-4 py-3 text-ink-secondary">{sched.steps.length}</td>
                                <td className="px-4 py-3 text-ink-muted">
                                    {sched.next_run_at ? formatRelativeTime(sched.next_run_at) : '—'}
                                </td>
                                <td className="px-4 py-3 text-ink-muted">
                                    {sched.last_run_at ? formatDateTime(sched.last_run_at) : 'Never'}
                                </td>
                                <td className="px-4 py-3">
                                    <button
                                        onClick={() => toggleMutation.mutate({ id: sched.id, enabled: !sched.enabled })}
                                        className={`text-xs font-medium ${sched.enabled ? 'text-status-good' : 'text-ink-muted'}`}
                                    >
                                        {sched.enabled ? 'Enabled' : 'Disabled'}
                                    </button>
                                </td>
                                <td className="px-4 py-3 text-right">
                                    <Button variant="ghost" onClick={() => setEditing(sched)}>
                                        Edit
                                    </Button>
                                    <Button
                                        variant="ghost"
                                        className="text-status-critical hover:text-status-critical"
                                        onClick={() => {
                                            if (confirm(`Delete schedule "${sched.name}"?`)) {
                                                deleteMutation.mutate(sched.id)
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
            {editing && <EditScheduleModal schedule={editing} onClose={() => setEditing(null)} />}
        </>
    )
}
