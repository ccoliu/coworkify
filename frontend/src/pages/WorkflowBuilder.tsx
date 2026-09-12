import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useCallback, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError, createWorkflow } from '../lib/apiClient'
import { defaultPayloadFor, useTaskTypeCatalog } from '../lib/taskTypeCatalog'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { Input, Label } from '../components/Field'
import { useWideLayout } from '../context/LayoutContext'
import { useToast } from '../context/ToastContext'
import { StepPropertiesPanel } from '../features/workflows/StepPropertiesPanel'
import { TaskTypePalette } from '../features/workflows/TaskTypePalette'
import { WorkflowBuilderCanvas } from '../features/workflows/WorkflowBuilderCanvas'
import { effectiveDependsOn } from '../features/workflows/WorkflowStepsEditor'
import { useStepsEditor } from '../features/workflows/useStepsEditor'

export function WorkflowBuilder() {
    useWideLayout()
    const navigate = useNavigate()
    const queryClient = useQueryClient()
    const { push } = useToast()
    const { data: taskTypes } = useTaskTypeCatalog()

    const [name, setName] = useState('')
    const [selectedUid, setSelectedUid] = useState<string | null>(null)
    // 空白畫布起手，所有節點都有明確的落點，不需要初始自動排版
    const { steps, updateStep, addStepOfType, removeStep, connectSteps, disconnectSteps } =
        useStepsEditor(() => [])

    const selectedStep = steps.find((s) => s.uid === selectedUid) ?? null

    const addStep = useCallback(
        (taskType: string) => {
            const spec = taskTypes?.find((t) => t.task_type === taskType)
            const seq = steps.filter((s) => s.taskType === taskType).length + 1
            return addStepOfType(taskType, defaultPayloadFor(spec), `${taskType}-${seq}`)
        },
        [taskTypes, steps, addStepOfType],
    )

    const mutation = useMutation({
        mutationFn: createWorkflow,
        onSuccess: (workflow) => {
            queryClient.invalidateQueries({ queryKey: ['workflows'] })
            push('Workflow created', 'success')
            navigate(`/workflows/${workflow.id}`)
        },
        onError: (err) => {
            push(err instanceof ApiError ? err.message : 'Failed to create workflow', 'error')
        },
    })

    function onSubmit(e: FormEvent) {
        e.preventDefault()
        mutation.mutate({
            name,
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

    const canSubmit = name.trim() !== '' && steps.length > 0 && steps.every((s) => s.name.trim() && s.taskType)

    return (
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <Link to="/workflows" className="text-sm text-ink-muted hover:text-ink">
                        ← Workflows
                    </Link>
                    <h1 className="mt-1 text-lg font-semibold text-ink">New workflow</h1>
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
                        {mutation.isPending ? 'Creating…' : 'Create workflow'}
                    </Button>
                </div>
            </div>

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
                                onUpdate={updateStep}
                                onRemove={(uid) => {
                                    removeStep(uid)
                                    setSelectedUid(null)
                                }}
                            />
                        </div>
                    )}
                </div>
            </Card>
        </form>
    )
}