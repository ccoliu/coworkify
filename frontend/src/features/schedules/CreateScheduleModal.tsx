import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { ApiError, createSchedule } from '../../lib/apiClient'
import { Button } from '../../components/Button'
import { Input, Label } from '../../components/Field'
import { Modal } from '../../components/Modal'
import { useToast } from '../../context/ToastContext'
import { effectiveDependsOn, makeStep, WorkflowStepsEditor } from '../workflows/WorkflowStepsEditor'
import { useStepsEditor } from '../workflows/useStepsEditor'

const CRON_PRESETS = [
    { label: 'Every day at 09:00', value: '0 9 * * *' },
    { label: 'Every hour', value: '0 * * * *' },
    { label: 'Every Monday at 09:00', value: '0 9 * * 1' },
]

export function CreateScheduleModal({ onClose }: { onClose: () => void }) {
    const queryClient = useQueryClient()
    const { push } = useToast()

    const [name, setName] = useState('')
    const [cron, setCron] = useState(CRON_PRESETS[0].value)
    const { steps, updateStep, addStep, removeStep, toggleDependsOn } = useStepsEditor(() => {
        const first = makeStep()
        return [first, makeStep([first.uid])]
    })

    const mutation = useMutation({
        mutationFn: createSchedule,
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
        mutation.mutate({
            name,
            cron_expression: cron,
            enabled: true,
            steps: steps.map((s) => ({
                key: s.uid,
                name: s.name,
                task_type: s.taskType,
                payload: s.payload,
                priority: s.priority,
                max_retries: s.maxRetries,
                depends_on: effectiveDependsOn(s),
                for_each: s.forEachUid ?? undefined,
                branch_of: s.branchOfUid ?? undefined,
                branch_when: s.branchWhen ?? undefined,
            })),
        })
    }

    const canSubmit = name.trim() && cron.trim() && steps.every((s) => s.name.trim() && s.taskType)

    return (
        <Modal
            title="New schedule"
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
                        form="create-schedule-form"
                        disabled={mutation.isPending || !canSubmit}
                    >
                        {mutation.isPending ? 'Creating…' : 'Create schedule'}
                    </Button>
                </>
            }
        >
            <form id="create-schedule-form" onSubmit={onSubmit} className="flex flex-col gap-4">
                <div>
                    <Label htmlFor="schedule-name">Schedule name</Label>
                    <Input
                        id="schedule-name"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="daily-job-search"
                        required
                    />
                </div>

                <div>
                    <Label htmlFor="schedule-cron">Cron expression</Label>
                    <Input
                        id="schedule-cron"
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
