import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { ApiError, getDefinition, updateSchedule } from '../../lib/apiClient'
import type { WorkflowSchedule } from '../../lib/types'
import { Button } from '../../components/Button'
import { Input, Label } from '../../components/Field'
import { Modal } from '../../components/Modal'
import { Spinner } from '../../components/Spinner'
import { useToast } from '../../context/ToastContext'
import { initialInput, missingRequired, RunInputFields } from '../workflows/runInput'

const CRON_PRESETS = [
    { label: 'Every day at 09:00', value: '0 9 * * *' },
    { label: 'Every hour', value: '0 * * * *' },
    { label: 'Every Monday at 09:00', value: '0 9 * * 1' },
]

export function EditScheduleModal({ schedule, onClose }: { schedule: WorkflowSchedule; onClose: () => void }) {
    const queryClient = useQueryClient()
    const { push } = useToast()

    const { data: definition, isLoading } = useQuery({
        queryKey: ['definition', schedule.definition_id],
        queryFn: () => getDefinition(schedule.definition_id as string),
        enabled: !!schedule.definition_id,
    })

    const [name, setName] = useState(schedule.name)
    const [cron, setCron] = useState(schedule.cron_expression)
    const [input, setInput] = useState<Record<string, unknown> | null>(schedule.input)

    const schema = definition?.input_schema ?? []
    // 定義新增欄位之後，舊排程的 input 會少那幾個 key，用預設值補起來
    const values = { ...initialInput(schema), ...(input ?? {}) }
    const missing = missingRequired(schema, values)

    const mutation = useMutation({
        mutationFn: () =>
            updateSchedule(schedule.id, {
                name,
                cron_expression: cron,
                ...(schema.length > 0 ? { input: values } : {}),
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

    const canSubmit = name.trim() && cron.trim() && missing.length === 0

    return (
        <Modal
            title="Edit schedule"
            onClose={onClose}
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
            {isLoading ? (
                <div className="flex items-center justify-center py-10">
                    <Spinner />
                </div>
            ) : (
                <form id="edit-schedule-form" onSubmit={onSubmit} className="flex flex-col gap-4">
                    <div>
                        <Label>Workflow</Label>
                        <p className="text-sm text-ink">
                            {definition?.name ?? schedule.definition_name ?? '—'}
                            {definition && <span className="text-ink-muted"> (v{definition.version})</span>}
                        </p>
                        <p className="mt-1 text-xs text-ink-muted">
                            要換成別條 workflow 的話，請建立一個新的排程。
                        </p>
                    </div>

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

                    <div className="flex flex-col gap-3 border-t border-border pt-4">
                        <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">Input</p>
                        <RunInputFields
                            idPrefix={`edit-schedule-input-${schedule.id}`}
                            schema={schema}
                            values={values}
                            onChange={setInput}
                            emptyHint="這個 workflow 沒有宣告輸入欄位，每次觸發都會用各步驟裡寫死的設定。"
                        />
                        {missing.length > 0 && (
                            <p className="text-xs text-status-critical">必填：{missing.join('、')}</p>
                        )}
                    </div>
                </form>
            )}
        </Modal>
    )
}
