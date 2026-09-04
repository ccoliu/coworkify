import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { ApiError, updateSchedule } from '../../lib/apiClient'
import type { WorkflowSchedule } from '../../lib/types'
import { Button } from '../../components/Button'
import { Input, Label } from '../../components/Field'
import { Modal } from '../../components/Modal'
import { useToast } from '../../context/ToastContext'
import { WorkflowStepsEditor, type StepDraft } from '../workflows/WorkflowStepsEditor'
import { useStepsEditor } from '../workflows/useStepsEditor'

const CRON_PRESETS = [
    { label: 'Every day at 09:00', value: '0 9 * * *' },
    { label: 'Every hour', value: '0 * * * *' },
    { label: 'Every Monday at 09:00', value: '0 9 * * 1' },
]

function stepsToDrafts(steps: WorkflowSchedule['steps']): StepDraft[] {
    return steps.map((s) => ({
        uid: s.key,
        name: s.name,
        taskType: s.task_type,
        payload: s.payload,
        priority: s.priority,
        maxRetries: s.max_retries,
        dependsOnUids: s.depends_on,
        forEachUid: s.for_each ?? null,
        runnerId: s.runner_id ?? null,
    }))
}

export function EditScheduleModal({ schedule, onClose }: { schedule: WorkflowSchedule; onClose: () => void }) {
    const queryClient = useQueryClient()
    const { push } = useToast()

    const [name, setName] = useState(schedule.name)
    const [cron, setCron] = useState(schedule.cron_expression)
    const { steps, updateStep, addStep, removeStep, toggleDependsOn } = useStepsEditor(() =>
        stepsToDrafts(schedule.steps),
    )

    const mutation = useMutation({
        mutationFn: () =>
            updateSchedule(schedule.id, {
                name,
                cron_expression: cron,
                steps: steps.map((s) => ({
                    key: s.uid,
                    name: s.name,
                    task_type: s.taskType,
                    payload: s.payload,
                    priority: s.priority,
                    max_retries: s.maxRetries,
                    depends_on: s.dependsOnUids,
                    for_each: s.forEachUid ?? undefined,
                    runner_id: s.runnerId ?? undefined,
                })),
            }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['schedules'] })
            push('Schedule updated', 'success')
            onClose()
        },
        onError: (err) => {
            push(err instanceof ApiError ? err.message : 'Failed to update schedule', 'error')
        },
    })

    function onSubmit(e: FormEvent) {
        e.preventDefault()
        mutation.mutate()
    }

    const canSubmit = name.trim() && cron.trim() && steps.every((s) => s.name.trim())

    return (
        <Modal
            title="Edit schedule"
            onClose={onClose}
            wide
            footer={
                <>
                    <Button variant="ghost" onClick={onClose}>
                        Cancel
                    </Button>
                    <Button
                        variant="primary"
                        type="submit"
                        form="edit-schedule-form"
                        disabled={mutation.isPending || !canSubmit}
                    >
                        {mutation.isPending ? 'Saving…' : 'Save changes'}
                    </Button>
                </>
            }
        >
            <form id="edit-schedule-form" onSubmit={onSubmit} className="flex flex-col gap-4">
                <div>
                    <Label htmlFor="edit-schedule-name">Schedule name</Label>
                    <Input id="edit-schedule-name" value={name} onChange={(e) => setName(e.target.value)} required />
                </div>

                <div>
                    <Label htmlFor="edit-schedule-cron">Cron expression</Label>
                    <Input
                        id="edit-schedule-cron"
                        value={cron}
                        onChange={(e) => setCron(e.target.value)}
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

                <WorkflowStepsEditor
                    steps={steps}
                    onUpdateStep={updateStep}
                    onRemoveStep={removeStep}
                    onToggleDependsOn={toggleDependsOn}
                    onAddStep={addStep}
                />
            </form>
        </Modal>
    )
}
