import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError, createDefinition, replaceDefinition } from '../lib/apiClient'
import { defaultPayloadFor, useTaskTypeCatalog } from '../lib/taskTypeCatalog'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { Input, Label } from '../components/Field'
import { useWideLayout } from '../context/LayoutContext'
import { useToast } from '../context/ToastContext'
import { StepPropertiesPanel } from '../features/workflows/StepPropertiesPanel'
import { TaskTypePalette } from '../features/workflows/TaskTypePalette'
import { WorkflowBuilderCanvas } from '../features/workflows/WorkflowBuilderCanvas'
import { useStepsEditor } from '../features/workflows/useStepsEditor'
import { fromStepCreates, toStepCreates, uniqueStepKey } from '../features/workflows/WorkflowStepsEditor'
import type { TaskFieldSpec, WorkflowDefinition } from '../lib/types'
import { InputSchemaEditor } from '../features/workflows/InputSchemaEditor'
import { issuesByUid, validateGraph, validateInputSchema } from '../features/workflows/validateGraph'

/**
 * 定義的畫布編輯器。沒給 definition = 新建（POST），有給 = 編輯（PUT 整份取代）。
 * 編輯既有定義的頁面要用 key={definition.id} 掛載，確保切換定義時狀態會重建。
 */
export function WorkflowBuilder({ definition }: { definition?: WorkflowDefinition }) {
    useWideLayout()
    const navigate = useNavigate()
    const queryClient = useQueryClient()
    const { push } = useToast()
    const { data: taskTypes } = useTaskTypeCatalog()
    const isEdit = definition != null

    const [name, setName] = useState(definition?.name ?? '')
    const [selectedUid, setSelectedUid] = useState<string | null>(null)
    const [description, setDescription] = useState(definition?.description ?? '')
    const [inputSchema, setInputSchema] = useState<TaskFieldSpec[]>(definition?.input_schema ?? [])
    const [showInputs, setShowInputs] = useState((definition?.input_schema.length ?? 0) > 0)

    const { steps, updateStep, addStepOfType, removeStep, connectSteps, disconnectSteps } =
        useStepsEditor(() => (definition ? fromStepCreates(definition.steps) : []))

    const selectedStep = steps.find((s) => s.uid === selectedUid) ?? null

    const issues = useMemo(
        () => [...validateGraph(steps), ...validateInputSchema(inputSchema, steps)],
        [steps, inputSchema],
    )
    const errors = useMemo(() => issues.filter((i) => i.severity !== 'warning'), [issues])
    const warnings = useMemo(() => issues.filter((i) => i.severity === 'warning'), [issues])
    const issueMap = useMemo(() => issuesByUid(errors), [errors])

    const addStep = useCallback(
        (taskType: string) => {
            const spec = taskTypes?.find((t) => t.task_type === taskType)
            const key = uniqueStepKey(taskType, new Set(steps.map((s) => s.key)))
            return addStepOfType(taskType, defaultPayloadFor(spec), key, key)
        },
        [taskTypes, steps, addStepOfType],
    )

    const duplicateStep = useCallback(
        (uid: string): string | null => {
            const src = steps.find((s) => s.uid === uid)
            if (!src) return null
            const key = uniqueStepKey(src.taskType, new Set(steps.map((s) => s.key)))
            // 只複製設定，連線刻意不複製——複製出來的是孤立節點，由使用者自己接
            const newUid = addStepOfType(src.taskType, { ...src.payload }, key, key)
            updateStep(newUid, { priority: src.priority, maxRetries: src.maxRetries })
            return newUid
        },
        [steps, addStepOfType, updateStep],
    )

    const mutation = useMutation({
        mutationFn: () => {
            const body = {
                name,
                steps: toStepCreates(steps),
                input_schema: inputSchema,
                description: description.trim() || null,
            }
            return isEdit ? replaceDefinition(definition.id, body) : createDefinition(body)
        },
        onSuccess: (saved) => {
            queryClient.invalidateQueries({ queryKey: ['definitions'] })
            queryClient.invalidateQueries({ queryKey: ['definition', saved.id] })
            push(isEdit ? `Saved (v${saved.version})` : 'Workflow created', 'success')
            navigate(`/definitions/${saved.id}`)
        },
        onError: (err) => {
            push(err instanceof ApiError ? err.message : 'Failed to save workflow', 'error')
        },
    })

    function onSubmit(e: FormEvent) {
        e.preventDefault()
        mutation.mutate()
    }

    const canSubmit = name.trim() !== '' && steps.length > 0 && errors.length === 0
    const backTo = isEdit ? `/definitions/${definition.id}` : '/workflows'

    return (
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <Link to={backTo} className="text-sm text-ink-muted hover:text-ink">
                        ← {isEdit ? definition.name : 'Workflows'}
                    </Link>
                    <h1 className="mt-1 text-lg font-semibold text-ink">
                        {isEdit ? `Edit workflow · v${definition.version}` : 'New workflow'}
                    </h1>
                </div>
                <div className="flex items-end gap-3">
                    <div>
                        <Label htmlFor="workflow-name">Workflow name</Label>
                        <Input
                            id="workflow-name"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="nightly-etl-pipeline"
                            required
                        />
                    </div>
                    <Button variant="primary" type="submit" disabled={mutation.isPending || !canSubmit}>
                        {mutation.isPending ? 'Saving…' : isEdit ? 'Save changes' : 'Create workflow'}
                    </Button>
                </div>
            </div>

            {errors.length > 0 && (
                <div className="rounded-lg border border-status-critical/40 bg-status-critical/5 px-4 py-3">
                    <p className="text-sm font-medium text-status-critical">
                        {errors.length} 個問題需要修正才能儲存
                    </p>
                    <ul className="mt-1.5 flex flex-col gap-0.5 text-xs text-status-critical">
                        {errors.map((issue, i) => (
                            <li key={`${issue.uid}-${i}`}>
                                <button
                                    type="button"
                                    disabled={!issue.uid}
                                    onClick={() => setSelectedUid(issue.uid)}
                                    className="text-left hover:underline disabled:cursor-default"
                                >
                                    •{' '}
                                    {issue.uid
                                        ? `${steps.find((s) => s.uid === issue.uid)?.name || 'step'}：${issue.message}`
                                        : issue.message}
                                </button>
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {warnings.length > 0 && (
                <div className="rounded-lg border border-status-warning/40 bg-status-warning/5 px-4 py-3">
                    <ul className="flex flex-col gap-0.5 text-xs text-status-warning">
                        {warnings.map((issue, i) => (
                            <li key={`${issue.uid}-${i}`}>
                                <button
                                    type="button"
                                    disabled={!issue.uid}
                                    onClick={() => setSelectedUid(issue.uid)}
                                    className="text-left hover:underline disabled:cursor-default"
                                >
                                    •{' '}
                                    {issue.uid
                                        ? `${steps.find((s) => s.uid === issue.uid)?.name || 'step'}：${issue.message}`
                                        : issue.message}
                                </button>
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            <Card className="p-0">
                <button
                    type="button"
                    onClick={() => setShowInputs((v) => !v)}
                    className="flex w-full items-center justify-between px-5 py-3 text-left"
                >
                    <span className="text-sm font-semibold text-ink">
                        Input fields{inputSchema.length > 0 && ` (${inputSchema.length})`}
                    </span>
                    <span className="text-xs text-ink-muted">{showInputs ? '收合' : '展開'}</span>
                </button>
                {showInputs && (
                    <div className="border-t border-border px-5 py-4">
                        <div className="mb-4">
                            <Label htmlFor="workflow-description">Description</Label>
                            <Input
                                id="workflow-description"
                                value={description}
                                onChange={(e) => setDescription(e.target.value)}
                                placeholder="這條 workflow 在做什麼（選填）"
                            />
                        </div>
                        <InputSchemaEditor schema={inputSchema} onChange={setInputSchema} />
                    </div>
                )}
            </Card>


            <Card className="overflow-hidden p-0">
                <div className="flex flex-col lg:h-[min(78vh,900px)] lg:flex-row">
                    <div className="shrink-0 overflow-y-auto border-b border-border lg:w-52 lg:border-b-0 lg:border-r">
                        <TaskTypePalette onAdd={addStep} />
                    </div>

                    <div className="h-[420px] min-w-0 flex-1 lg:h-auto">
                        <WorkflowBuilderCanvas
                            steps={steps}
                            selectedUid={selectedUid}
                            onSelect={setSelectedUid}
                            onAddStep={addStep}
                            onDuplicateStep={duplicateStep}
                            issues={issueMap}
                            autoLayoutOnLoad={isEdit}
                            onRemoveStep={(uid) => {
                                removeStep(uid)
                                setSelectedUid((cur) => (cur === uid ? null : cur))
                            }}
                            onConnectSteps={connectSteps}
                            onDisconnectSteps={disconnectSteps}
                            onInvalid={(message) => push(message, 'error')}
                        />
                    </div>

                    {selectedStep && (
                        <div className="shrink-0 border-t border-border bg-surface lg:w-80 lg:border-l lg:border-t-0">
                            <StepPropertiesPanel
                                step={selectedStep}
                                steps={steps}
                                issues={issueMap.get(selectedStep.uid) ?? []}
                                onUpdate={updateStep}
                                onRemove={(uid) => {
                                    removeStep(uid)
                                    setSelectedUid(null)
                                }}
                            />
                        </div>
                    )}
                </div>

                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-1 text-xs text-ink-muted">
                    {[
                        ['Delete', '刪除選取的節點或連線'],
                        ['Esc', '取消選取'],
                        ['Ctrl+D', '複製節點'],
                        ['L', '自動排版'],
                        ['F', '置中'],
                    ].map(([key, label]) => (
                        <span key={key} className="flex items-center gap-1.5">
                            <kbd className="rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-[10px] text-ink-secondary">
                                {key}
                            </kbd>
                            {label}
                        </span>
                    ))}
                </div>
            </Card>
        </form>
    )
}
