import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, createWorkflow } from '../../lib/apiClient'
import { TASK_TYPES } from '../../lib/types'
import { Button } from '../../components/Button'
import { Input, Label, Select } from '../../components/Field'
import { Modal } from '../../components/Modal'
import { useToast } from '../../context/ToastContext'
import { defaultPayload, PAYLOAD_SPECS } from '../tasks/taskTypePayloads'

interface StepDraft {
    uid: string
    name: string
    taskType: string
    payload: Record<string, unknown>
    priority: number
    maxRetries: number
    dependsOnUids: string[]
}

function makeStep(dependsOn: string[] = []): StepDraft {
    return {
        uid: crypto.randomUUID(),
        name: '',
        taskType: TASK_TYPES[0],
        payload: defaultPayload(TASK_TYPES[0]),
        priority: 3,
        maxRetries: 3,
        dependsOnUids: dependsOn,
    }
}

export function CreateWorkflowModal({ onClose }: { onClose: () => void }) {
    const queryClient = useQueryClient()
    const navigate = useNavigate()
    const { push } = useToast()

    const [name, setName] = useState('')
    const [steps, setSteps] = useState<StepDraft[]>(() => {
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

    function updateStep(uid: string, patch: Partial<StepDraft>) {
        setSteps((prev) => prev.map((s) => (s.uid === uid ? { ...s, ...patch } : s)))
    }

    function addStep() {
        setSteps((prev) => [...prev, makeStep(prev.length > 0 ? [prev[prev.length - 1].uid] : [])])
    }

    function removeStep(uid: string) {
        setSteps((prev) =>
            prev
                .filter((s) => s.uid !== uid)
                .map((s) => ({ ...s, dependsOnUids: s.dependsOnUids.filter((d) => d !== uid) })),
        )
    }

    function toggleDependsOn(uid: string, depUid: string) {
        setSteps((prev) =>
            prev.map((s) =>
                s.uid === uid
                    ? {
                        ...s,
                        dependsOnUids: s.dependsOnUids.includes(depUid)
                            ? s.dependsOnUids.filter((d) => d !== depUid)
                            : [...s.dependsOnUids, depUid],
                    }
                    : s,
            ),
        )
    }

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
                depends_on: s.dependsOnUids,
            })),
        })
    }

    const canSubmit = name.trim() && steps.every((s) => s.name.trim())

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

                <div className="flex flex-col gap-3">
                    {steps.map((step, i) => {
                        const spec = PAYLOAD_SPECS[step.taskType] ?? []
                        const priorSteps = steps.filter((s) => s.uid !== step.uid)
                        return (
                            <div key={step.uid} className="rounded-lg border border-border p-3">
                                <div className="mb-3 flex items-center justify-between">
                                    <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
                                        Step {i + 1}
                                    </p>
                                    {steps.length > 1 && (
                                        <button
                                            type="button"
                                            onClick={() => removeStep(step.uid)}
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
                                                onChange={(e) => updateStep(step.uid, { name: e.target.value })}
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
                                                    updateStep(step.uid, {
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
                                                                updateStep(step.uid, {
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
                                                                updateStep(step.uid, {
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

                                    {priorSteps.length > 0 && (
                                        <div>
                                            <Label>Depends on</Label>
                                            <div className="flex flex-wrap gap-3">
                                                {priorSteps.map((other) => (
                                                    <label key={other.uid} className="flex items-center gap-1.5 text-sm text-ink-secondary">
                                                        <input
                                                            type="checkbox"
                                                            checked={step.dependsOnUids.includes(other.uid)}
                                                            onChange={() => toggleDependsOn(step.uid, other.uid)}
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
                </div>

                <Button type="button" variant="secondary" onClick={addStep}>
                    + Add step
                </Button>
            </form>
        </Modal>
    )
}
