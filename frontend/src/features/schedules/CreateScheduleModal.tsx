import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { ApiError, createSchedule, listDefinitions } from '../../lib/apiClient'
import { Button } from '../../components/Button'
import { Input, Label, Select } from '../../components/Field'
import { Modal } from '../../components/Modal'
import { Spinner } from '../../components/Spinner'
import { useToast } from '../../context/ToastContext'
import { initialInput, missingRequired, RunInputFields } from '../workflows/runInput'

const CRON_PRESETS = [
    { label: 'Every day at 09:00', value: '0 9 * * *' },
    { label: 'Every hour', value: '0 * * * *' },
    { label: 'Every Monday at 09:00', value: '0 9 * * 1' },
]

export function CreateScheduleModal({ onClose }: { onClose: () => void }) {
    const queryClient = useQueryClient()
    const { push } = useToast()

    const { data: definitions, isLoading } = useQuery({
        queryKey: ['definitions'],
        queryFn: () => listDefinitions(100),
    })

    const [definitionId, setDefinitionId] = useState('')
    const [name, setName] = useState('')
    const [cron, setCron] = useState(CRON_PRESETS[0].value)
    // null = 使用者還沒動過，顯示該定義的預設值
    const [input, setInput] = useState<Record<string, unknown> | null>(null)

    const definition = definitions?.find((d) => d.id === definitionId) ?? null
    const schema = definition?.input_schema ?? []
    const values = input ?? initialInput(schema)
    const missing = missingRequired(schema, values)

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
        mutation.mutate({ name, cron_expression: cron, definition_id: definitionId, input: values, enabled: true })
    }

    const canSubmit = name.trim() && cron.trim() && definitionId && missing.length === 0

    return (
        <Modal
            title="New schedule"
            onClose={onClose}
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
            {isLoading ? (
                <div className="flex items-center justify-center py-10">
                    <Spinner />
                </div>
            ) : (
                <form id="create-schedule-form" onSubmit={onSubmit} className="flex flex-col gap-4">
                    <div>
                        <Label htmlFor="schedule-definition">Workflow</Label>
                        <Select
                            id="schedule-definition"
                            value={definitionId}
                            onChange={(e) => {
                                setDefinitionId(e.target.value)
                                // 換一條產線，輸入欄位整組不同，舊的值不能留
                                setInput(null)
                                const picked = definitions?.find((d) => d.id === e.target.value)
                                if (picked && !name.trim()) setName(picked.name)
                            }}
                            required
                        >
                            <option value="">— pick a workflow —</option>
                            {(definitions ?? []).map((d) => (
                                <option key={d.id} value={d.id}>
                                    {d.name} (v{d.version})
                                </option>
                            ))}
                        </Select>
                        <p className="mt-1 text-xs text-ink-muted">
                            排程指向這條 workflow 本身，不是它現在的快照——之後改了它，下次觸發就會用新版。
                        </p>
                    </div>

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

                    {definition && (
                        <div className="flex flex-col gap-3 border-t border-border pt-4">
                            <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">Input</p>
                            <RunInputFields
                                idPrefix={`schedule-input-${definition.id}`}
                                schema={schema}
                                values={values}
                                onChange={setInput}
                                emptyHint="這個 workflow 沒有宣告輸入欄位，每次觸發都會用各步驟裡寫死的設定。"
                            />
                            {missing.length > 0 && (
                                <p className="text-xs text-status-critical">必填：{missing.join('、')}</p>
                            )}
                        </div>
                    )}
                </form>
            )}
        </Modal>
    )
}
