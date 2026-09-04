import { TASK_TYPES } from '../../lib/types'
import { Button } from '../../components/Button'
import { Input, Label, Select } from '../../components/Field'
import { defaultPayload, PAYLOAD_SPECS } from '../tasks/taskTypePayloads'

export interface StepDraft {
    uid: string
    name: string
    taskType: string
    payload: Record<string, unknown>
    priority: number
    maxRetries: number
    dependsOnUids: string[]
    forEachUid: string | null
}

export function makeStep(dependsOn: string[] = []): StepDraft {
    return {
        uid: crypto.randomUUID(),
        name: '',
        taskType: TASK_TYPES[0],
        payload: defaultPayload(TASK_TYPES[0]),
        priority: 3,
        maxRetries: 3,
        dependsOnUids: dependsOn,
        forEachUid: null,
    }
}

interface WorkflowStepsEditorProps {
    steps: StepDraft[]
    onUpdateStep: (uid: string, patch: Partial<StepDraft>) => void
    onRemoveStep: (uid: string) => void
    onToggleDependsOn: (uid: string, depUid: string) => void
    onAddStep: () => void
}

export function WorkflowStepsEditor({
    steps,
    onUpdateStep,
    onRemoveStep,
    onToggleDependsOn,
    onAddStep,
}: WorkflowStepsEditorProps) {
    return (
        <div className="flex flex-col gap-3">
            {steps.map((step, i) => {
                const spec = PAYLOAD_SPECS[step.taskType] ?? []
                // 可以被選為 for_each 來源的 step：不是自己、也不能是另一個動態展開步驟
                const forEachCandidates = steps.filter((s) => s.uid !== step.uid && !s.forEachUid)
                // depends on 候選名單：一般步驟只能依賴其他一般步驟；
                // 動態展開步驟（有設 forEachUid）只能依賴同一組（forEachUid 相同）的其他動態步驟
                const dependsOnCandidates = steps.filter((s) => {
                    if (s.uid === step.uid) return false
                    return step.forEachUid ? s.forEachUid === step.forEachUid : !s.forEachUid
                })
                return (
                    <div key={step.uid} className="rounded-lg border border-border p-3">
                        <div className="mb-3 flex items-center justify-between">
                            <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
                                Step {i + 1}
                            </p>
                            {steps.length > 1 && (
                                <button
                                    type="button"
                                    onClick={() => onRemoveStep(step.uid)}
                                    className="text-xs font-medium text-ink-muted hover:text-status-critical"
                                >
                                    Remove
                                </button>
                            )}
                        </div>

                        <div className="flex flex-col gap-3">
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <Label htmlFor={`step-name-${step.uid}`}>Name</Label>
                                    <Input
                                        id={`step-name-${step.uid}`}
                                        value={step.name}
                                        onChange={(e) => onUpdateStep(step.uid, { name: e.target.value })}
                                        placeholder={`step-${i + 1}`}
                                        required
                                    />
                                </div>
                                <div>
                                    <Label htmlFor={`step-type-${step.uid}`}>Task type</Label>
                                    <Select
                                        id={`step-type-${step.uid}`}
                                        value={step.taskType}
                                        onChange={(e) =>
                                            onUpdateStep(step.uid, {
                                                taskType: e.target.value,
                                                payload: defaultPayload(e.target.value),
                                            })
                                        }
                                    >
                                        {TASK_TYPES.map((t) => (
                                            <option key={t} value={t}>
                                                {t}
                                            </option>
                                        ))}
                                    </Select>
                                </div>
                            </div>

                            {forEachCandidates.length > 0 && (
                                <div>
                                    <Label htmlFor={`step-foreach-${step.uid}`}>For each item from</Label>
                                    <Select
                                        id={`step-foreach-${step.uid}`}
                                        value={step.forEachUid ?? ''}
                                        onChange={(e) => {
                                            const forEachUid = e.target.value || null
                                            onUpdateStep(step.uid, {
                                                forEachUid,
                                                // 切換 for_each 分組後，清掉不再合法的 depends_on
                                                dependsOnUids: step.dependsOnUids.filter((uid) => {
                                                    const other = steps.find((s) => s.uid === uid)
                                                    return other ? other.forEachUid === forEachUid : false
                                                }),
                                            })
                                        }}
                                    >
                                        <option value="">— regular step —</option>
                                        {forEachCandidates.map((other) => (
                                            <option key={other.uid} value={other.uid}>
                                                {other.name.trim() || `step-${steps.indexOf(other) + 1}`}
                                            </option>
                                        ))}
                                    </Select>
                                    {step.forEachUid && (
                                        <p className="mt-1 text-xs text-ink-muted">
                                            此步驟會依上面 step 的執行結果（須為 list）逐項展開；payload 可用{' '}
                                            <code className="font-mono">{'{{item.欄位}}'}</code> 參照該項目的值。
                                        </p>
                                    )}
                                </div>
                            )}

                            {spec.length > 0 && (
                                <div className="grid grid-cols-2 gap-3">
                                    {spec.map((field) => (
                                        <div key={field.key}>
                                            <Label htmlFor={`step-${step.uid}-${field.key}`}>{field.label}</Label>
                                            {field.kind === 'boolean' ? (
                                                <Select
                                                    id={`step-${step.uid}-${field.key}`}
                                                    value={String(step.payload[field.key])}
                                                    onChange={(e) =>
                                                        onUpdateStep(step.uid, {
                                                            payload: { ...step.payload, [field.key]: e.target.value === 'true' },
                                                        })
                                                    }
                                                >
                                                    <option value="false">false</option>
                                                    <option value="true">true</option>
                                                </Select>
                                            ) : (
                                                <Input
                                                    id={`step-${step.uid}-${field.key}`}
                                                    type={field.kind === 'number' ? 'number' : 'text'}
                                                    value={String(step.payload[field.key] ?? '')}
                                                    onChange={(e) =>
                                                        onUpdateStep(step.uid, {
                                                            payload: {
                                                                ...step.payload,
                                                                [field.key]:
                                                                    field.kind === 'number' ? Number(e.target.value) : e.target.value,
                                                            },
                                                        })
                                                    }
                                                />
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}

                            {dependsOnCandidates.length > 0 && (
                                <div>
                                    <Label>Depends on</Label>
                                    <div className="flex flex-wrap gap-3">
                                        {dependsOnCandidates.map((other) => (
                                            <label key={other.uid} className="flex items-center gap-1.5 text-sm text-ink-secondary">
                                                <input
                                                    type="checkbox"
                                                    checked={step.dependsOnUids.includes(other.uid)}
                                                    onChange={() => onToggleDependsOn(step.uid, other.uid)}
                                                />
                                                {other.name.trim() || `step-${steps.indexOf(other) + 1}`}
                                            </label>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                )
            })}

            <Button type="button" variant="secondary" onClick={onAddStep}>
                + Add step
            </Button>
        </div>
    )
}
