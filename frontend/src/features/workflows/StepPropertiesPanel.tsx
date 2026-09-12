import { defaultPayloadFor, useTaskTypeCatalog } from '../../lib/taskTypeCatalog'
import { Button } from '../../components/Button'
import { Input, Label, Select } from '../../components/Field'
import { TaskPayloadFields } from '../tasks/TaskPayloadFields'
import type { StepDraft } from './WorkflowStepsEditor'

interface Props {
    step: StepDraft
    steps: StepDraft[]
    onUpdate: (uid: string, patch: Partial<StepDraft>) => void
    onRemove: (uid: string) => void
}

export function StepPropertiesPanel({ step, steps, onUpdate, onRemove }: Props) {
    const { data: taskTypes } = useTaskTypeCatalog()
    const spec = taskTypes?.find((t) => t.task_type === step.taskType)

    const byUid = new Map(steps.map((s) => [s.uid, s]))
    const nameOf = (uid: string) => byUid.get(uid)?.name.trim() || 'step'
    // for_each 來源：不能是自己，也不能是另一個展開步驟
    const forEachCandidates = steps.filter((s) => s.uid !== step.uid && !s.forEachUid)

    return (
        <div className="flex h-full flex-col">
            <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2.5">
                <p className="truncate text-sm font-medium text-ink">Step settings</p>
                <Button variant="ghost" onClick={() => onRemove(step.uid)}>
                    Delete
                </Button>
            </div>

            <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-3 py-3">
                <div>
                    <Label htmlFor="step-name">Name</Label>
                    <Input
                        id="step-name"
                        value={step.name}
                        onChange={(e) => onUpdate(step.uid, { name: e.target.value })}
                        placeholder="step-1"
                    />
                </div>

                <div>
                    <Label htmlFor="step-type">Task type</Label>
                    <Select
                        id="step-type"
                        value={step.taskType}
                        onChange={(e) => {
                            const next = taskTypes?.find((t) => t.task_type === e.target.value)
                            // 換型別等於換一組 payload 欄位，舊值留著只會送出垃圾
                            onUpdate(step.uid, { taskType: e.target.value, payload: defaultPayloadFor(next) })
                        }}
                    >
                        {(taskTypes ?? []).map((t) => (
                            <option key={t.task_type} value={t.task_type}>
                                {t.label}
                            </option>
                        ))}
                    </Select>
                </div>

                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <Label htmlFor="step-priority">Priority</Label>
                        <Input
                            id="step-priority"
                            type="number"
                            min={0}
                            value={step.priority}
                            onChange={(e) => onUpdate(step.uid, { priority: Number(e.target.value) })}
                        />
                    </div>
                    <div>
                        <Label htmlFor="step-retries">Max retries</Label>
                        <Input
                            id="step-retries"
                            type="number"
                            min={0}
                            value={step.maxRetries}
                            onChange={(e) => onUpdate(step.uid, { maxRetries: Number(e.target.value) })}
                        />
                    </div>
                </div>

                {forEachCandidates.length > 0 && (
                    <div>
                        <Label htmlFor="step-foreach">For each item from</Label>
                        <Select
                            id="step-foreach"
                            value={step.forEachUid ?? ''}
                            onChange={(e) => {
                                const forEachUid = e.target.value || null
                                onUpdate(step.uid, {
                                    forEachUid,
                                    // 切換分組後，跨組的依賴不再合法，清掉
                                    dependsOnUids: step.dependsOnUids.filter(
                                        (uid) => (byUid.get(uid)?.forEachUid ?? null) === forEachUid,
                                    ),
                                })
                            }}
                        >
                            <option value="">— regular step —</option>
                            {forEachCandidates.map((other) => (
                                <option key={other.uid} value={other.uid}>
                                    {nameOf(other.uid)}
                                </option>
                            ))}
                        </Select>
                        {step.forEachUid && (
                            <p className="mt-1 text-xs text-ink-muted">
                                依上游結果（須為 list）逐項展開；payload 可用{' '}
                                <code className="font-mono">{'{{item.欄位}}'}</code> 參照該項目。
                            </p>
                        )}
                    </div>
                )}

                {step.branchOfUid && (
                    <div className="rounded-lg bg-plane px-3 py-2 text-xs text-ink-secondary">
                        分支：只有在 <span className="font-medium">{nameOf(step.branchOfUid)}</span> 結果為{' '}
                        <span className="font-mono">{step.branchWhen}</span> 時執行。
                        <br />
                        在畫布上刪掉那條邊即可解除。
                    </div>
                )}

                {step.dependsOnUids.length > 0 && (
                    <div>
                        <Label>Depends on</Label>
                        <p className="text-sm text-ink-secondary">
                            {step.dependsOnUids.map(nameOf).join('、')}
                        </p>
                        <p className="mt-1 text-xs text-ink-muted">在畫布上拉線／刪線來調整</p>
                    </div>
                )}

                {spec && spec.fields.length > 0 && (
                    <div className="border-t border-border pt-3">
                        <TaskPayloadFields
                            idPrefix={`step-${step.uid}`}
                            fields={spec.fields}
                            payload={step.payload}
                            onChange={(payload) => onUpdate(step.uid, { payload })}
                        />
                    </div>
                )}
            </div>
        </div>
    )
}