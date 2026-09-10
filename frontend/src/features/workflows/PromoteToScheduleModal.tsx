import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { ApiError, promoteWorkflowToSchedule } from '../../lib/apiClient'
import { Button } from '../../components/Button'
import { Input, Label } from '../../components/Field'
import { Modal } from '../../components/Modal'
import { useToast } from '../../context/ToastContext'

const CRON_PRESETS = [
    { label: 'Every day at 09:00', value: '0 9 * * *' },
    { label: 'Every hour', value: '0 * * * *' },
    { label: 'Every Monday at 09:00', value: '0 9 * * 1' },
]

/**
 * Registers an already-created workflow as a recurring schedule, reusing its
 * stored step template — no re-entering the steps, unlike CreateScheduleModal.
 */
export function PromoteToScheduleModal({
    workflowId,
    workflowName,
    onClose,
}: {
    workflowId: string
    workflowName: string
    onClose: () => void
}) {
    const queryClient = useQueryClient()
    const { push } = useToast()

    const [name, setName] = useState(workflowName)
    const [cron, setCron] = useState(CRON_PRESETS[0].value)

    const mutation = useMutation({
        mutationFn: () => promoteWorkflowToSchedule(workflowId, { name, cron_expression: cron, enabled: true }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['schedules'] })
            push('Schedule created', 'success')
            onClose()
        },
        onError: (err) => {
            push(err instanceof ApiError ? err.message : 'Failed to create schedule', 'error')
        },
    })

    function onSubmit(e: FormEvent) {
        e.preventDefault()
        mutation.mutate()
    }

    const canSubmit = name.trim() && cron.trim()

    return (
        <Modal
            title="Schedule this workflow"
            onClose={onClose}
            footer={
                <>
                    <Button variant="ghost" onClick={onClose}>
                        Cancel
                    </Button>
                    <Button
                        variant="primary"
                        type="submit"
                        form="promote-to-schedule-form"
                        disabled={mutation.isPending || !canSubmit}
                    >
                        {mutation.isPending ? 'Creating…' : 'Create schedule'}
                    </Button>
                </>
            }
        >
            <form id="promote-to-schedule-form" onSubmit={onSubmit} className="flex flex-col gap-4">
                <p className="text-sm text-ink-secondary">
                    Reuses this workflow&apos;s steps as-is — edit them from the Schedules page afterward if needed.
                </p>
                <div>
                    <Label htmlFor="promote-schedule-name">Schedule name</Label>
                    <Input
                        id="promote-schedule-name"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        required
                    />
                </div>
                <div>
                    <Label htmlFor="promote-schedule-cron">Cron expression</Label>
                    <Input
                        id="promote-schedule-cron"
                        value={cron}
                        onChange={(e) => setCron(e.target.value)}
                        placeholder="0 9 * * *"
                        required
                        className="font-mono"
                    />
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {CRON_PRESETS.map((preset) => (
                            <button
                                key={preset.value}
                                type="button"
                                onClick={() => setCron(preset.value)}
                                className="rounded-full border border-border px-2.5 py-1 text-xs text-ink-secondary hover:bg-surface"
                            >
                                {preset.label}
                            </button>
                        ))}
                    </div>
                </div>
            </form>
        </Modal>
    )
}
