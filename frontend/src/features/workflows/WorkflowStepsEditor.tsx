import { useEffect } from 'react'
import { defaultPayloadFor, useTaskTypeCatalog } from '../../lib/taskTypeCatalog'
import { Button } from '../../components/Button'
import { Input, Label, Select } from '../../components/Field'
import { Spinner } from '../../components/Spinner'
import { TaskPayloadFields } from '../tasks/TaskPayloadFields'
import type { WorkflowStepCreate } from '../../lib/types'

export interface StepDraft {
    uid: string
    /** 送給後端的 step key，也是 payload 裡 '{{steps.<key>.result}}' 要寫的名字。
     *  只能是英數字與底線——後端的參照 regex 不吃連字號。 */
    key: string
    name: string
    taskType: string
    payload: Record<string, unknown>
    priority: number
    maxRetries: number
    dependsOnUids: string[]
    forEachUid: string | null
    branchOfUid: string | null
    branchWhen: 'true' | 'false' | null
}

export function makeStep(dependsOn: string[] = []): StepDraft {
    return {
        uid: crypto.randomUUID(),
        key: '',
        // 這裡先留空，等 WorkflowStepsEditor 拿到 task-type 目錄後用第一個類型回填——
        // makeStep 是給 useState 初始化用的純函式，沒辦法在這裡呼叫 hook 抓目錄。
        name: '',
        taskType: '',
        payload: {},
        priority: 3,
        maxRetries: 3,
        dependsOnUids: dependsOn,
        forEachUid: null,
        branchOfUid: null,
        branchWhen: null,
    }
}

/** 提交前用這個算出實際要送出的 depends_on：一定含 branchOfUid，不管使用者有沒有手動勾選它。 */
export function effectiveDependsOn(step: StepDraft): string[] {
    if (step.branchOfUid && !step.dependsOnUids.includes(step.branchOfUid)) {
        return [...step.dependsOnUids, step.branchOfUid]
    }
    return step.dependsOnUids
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
    const { data: taskTypes, isLoading } = useTaskTypeCatalog()

    // 目錄載入回來之前建立的 step（含每次按「+ Add step」新增的）taskType 都是空的，
    // 這裡統一補上第一個類型當預設值。
    useEffect(() => {
        if (!taskTypes || taskTypes.length === 0) return
        for (const step of steps) {
            if (!step.taskType) {
                onUpdateStep(step.uid, { taskType: taskTypes[0].task_type, payload: defaultPayloadFor(taskTypes[0]) })
            }
        }
    }, [taskTypes, steps, onUpdateStep])

    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-8">
                <Spinner />
            </div>
        )
    }

    return (
        <div className="flex flex-col gap-3">
            {steps.map((step, i) => {
                const spec = taskTypes?.find((t) => t.task_type === step.taskType)
                // 可以被選為 for_each 來源的 step：不是自己、也不能是另一個動態展開步驟
                const forEachCandidates = steps.filter((s) => s.uid !== step.uid && !s.forEachUid)
                // 可以被選為分支來源的 step：condition 類型、不是自己
                const branchCandidates = steps.filter((s) => s.uid !== step.uid && s.taskType === 'condition')
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
                                        onChange={(e) => {
                                            const nextSpec = taskTypes?.find((t) => t.task_type === e.target.value)
                                            onUpdateStep(step.uid, {
                                                taskType: e.target.value,
                                                payload: defaultPayloadFor(nextSpec),
                                            })
                                        }}
                                    >
                                        {(taskTypes ?? []).map((t) => (
                                            <option key={t.task_type} value={t.task_type}>
                                                {t.label}
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

                            {branchCandidates.length > 0 && (
                                <div>
                                    <Label htmlFor={`step-branch-${step.uid}`}>Branch on condition</Label>
                                    <div className="flex gap-2">
                                        <Select
                                            id={`step-branch-${step.uid}`}
                                            value={step.branchOfUid ?? ''}
                                            onChange={(e) => {
                                                const branchOfUid = e.target.value || null
                                                onUpdateStep(step.uid, {
                                                    branchOfUid,
                                                    branchWhen: branchOfUid ? (step.branchWhen ?? 'true') : null,
                                                })
                                            }}
                                        >
                                            <option value="">— no branch —</option>
                                            {branchCandidates.map((other) => (
                                                <option key={other.uid} value={other.uid}>
                                                    {other.name.trim() || `step-${steps.indexOf(other) + 1}`}
                                                </option>
                                            ))}
                                        </Select>
                                        {step.branchOfUid && (
                                            <Select
                                                className="w-32"
                                                value={step.branchWhen ?? 'true'}
                                                onChange={(e) =>
                                                    onUpdateStep(step.uid, { branchWhen: e.target.value as 'true' | 'false' })
                                                }
                                            >
                                                <option value="true">if true</option>
                                                <option value="false">if false</option>
                                            </Select>
                                        )}
                                    </div>
                                    {step.branchOfUid && (
                                        <p className="mt-1 text-xs text-ink-muted">
                                            只有在上面那個 condition 結果符合時這個步驟才會執行；不符合會被取消（連同它的下游）。
                                        </p>
                                    )}
                                </div>
                            )}

                            {spec && spec.fields.length > 0 && (
                                <TaskPayloadFields
                                    idPrefix={`step-${step.uid}`}
                                    fields={spec.fields}
                                    payload={step.payload}
                                    onChange={(payload) => onUpdateStep(step.uid, { payload })}
                                />
                            )}

                            {dependsOnCandidates.length > 0 && (
                                <div>
                                    <Label>Depends on</Label>
                                    <div className="flex flex-wrap gap-3">
                                        {dependsOnCandidates.map((other) => {
                                            const lockedByBranch = other.uid === step.branchOfUid
                                            return (
                                                <label key={other.uid} className="flex items-center gap-1.5 text-sm text-ink-secondary">
                                                    <input
                                                        type="checkbox"
                                                        checked={lockedByBranch || step.dependsOnUids.includes(other.uid)}
                                                        disabled={lockedByBranch}
                                                        onChange={() => onToggleDependsOn(step.uid, other.uid)}
                                                    />
                                                    {other.name.trim() || `step-${steps.indexOf(other) + 1}`}
                                                    {lockedByBranch && ' (branch)'}
                                                </label>
                                            )
                                        })}
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

/** 在既有的 key 之中挑一個沒被用過的 `<base>_<n>`。 */
export function uniqueStepKey(base: string, taken: Set<string>): string {
    const safe = base.replace(/[^a-zA-Z0-9_]+/g, '_') || 'step'
    let i = 1
    while (taken.has(`${safe}_${i}`)) i += 1
    return `${safe}_${i}`
}

/**
 * 送出用：畫布內部一律用 uid 互相參照，後端只認 step key，這裡做最後轉換。
 * 不能直接送 uid——uid 是 UUID，帶連字號，後端的 '{{steps.<key>.result}}'
 * regex（app/schemas/workflow.py 的 _STEP_REF）比對不到。
 */
export function toStepCreates(steps: StepDraft[]): WorkflowStepCreate[] {
    const keyByUid = new Map(steps.map((s) => [s.uid, s.key]))
    const toKeys = (uids: string[]) =>
        uids.flatMap((uid) => {
            const key = keyByUid.get(uid)
            return key ? [key] : []
        })

    return steps.map((s) => ({
        key: s.key,
        name: s.name,
        task_type: s.taskType,
        payload: s.payload,
        priority: s.priority,
        max_retries: s.maxRetries,
        depends_on: toKeys(effectiveDependsOn(s)),
        for_each: s.forEachUid ? keyByUid.get(s.forEachUid) : undefined,
        branch_of: s.branchOfUid ? keyByUid.get(s.branchOfUid) : undefined,
        branch_when: s.branchWhen ?? undefined,
    }));
}

/**
 * 載入用：toStepCreates 的反向。後端的 key 參照換回畫布內部的 uid。
 * 不支援 reduce_of（StepDraft 沒有這個欄位）——呼叫端要先用 hasUnsupportedSteps 擋掉，
 * 否則存回去會把 reduce 設定洗掉。
 */
export function fromStepCreates(creates: WorkflowStepCreate[]): StepDraft[] {
    const uidByKey = new Map(creates.map((c) => [c.key, crypto.randomUUID()]))
    const toUid = (key?: string | null) => (key ? uidByKey.get(key) : null) ?? null;


    return creates.map((c) => ({
        uid: uidByKey.get(c.key)!,
        key: c.key,
        name: c.name,
        taskType: c.task_type,
        payload: c.payload,
        priority: c.priority,
        maxRetries: c.max_retries,
        dependsOnUids: c.depends_on.flatMap((k) => {
            const uid = uidByKey.get(k)
            return uid ? [uid] : []
        }),
        forEachUid: toUid(c.for_each),
        branchOfUid: toUid(c.branch_of),
        branchWhen: c.branch_when ?? null,
    }))
}

export function hasUnsupportedSteps(creates: WorkflowStepCreate[]): boolean {
    return creates.some((c) => c.reduce_of != null);
}