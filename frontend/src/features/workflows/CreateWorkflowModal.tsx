import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, createWorkflow } from '../../lib/apiClient'
import { Button } from '../../components/Button'
import { Input, Label } from '../../components/Field'
import { Modal } from '../../components/Modal'
import { useToast } from '../../context/ToastContext'
import { effectiveDependsOn, makeStep, WorkflowStepsEditor } from './WorkflowStepsEditor'
import { useStepsEditor } from './useStepsEditor'

export function CreateWorkflowModal({ onClose }: { onClose: () => void }) {
    const queryClient = useQueryClient()
    const navigate = useNavigate()
    const { push } = useToast()

    const [name, setName] = useState('')
    const { steps, updateStep, addStep, removeStep, toggleDependsOn } = useStepsEditor(() => {
        const first = makeStep()
        return [first, makeStep([first.uid])]
    })

    const mutation = useMutation({
        mutationFn: createWorkflow,
        onSuccess: (workflow) => {
            queryClient.invalidateQueries({ queryKey: ['workflows'] })
            push('Workflow created', 'success')
            onClose()
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

    const canSubmit = name.trim() && steps.every((s) => s.name.trim() && s.taskType)

    return (
        <Modal
            title="New workflow"
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
                        form="create-workflow-form"
                        disabled={mutation.isPending || !canSubmit}
                    >
                        {mutation.isPending ? 'Creating…' : 'Create workflow'}
                    </Button>
                </>
            }
        >
            <form id="create-workflow-form" onSubmit={onSubmit} className="flex flex-col gap-4">
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
