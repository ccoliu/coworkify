import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { ApiError, createTask } from '../../lib/apiClient'
import { TASK_TYPES } from '../../lib/types'
import { Button } from '../../components/Button'
import { Input, Label, Select } from '../../components/Field'
import { Modal } from '../../components/Modal'
import { useToast } from '../../context/ToastContext'
import { defaultPayload, PAYLOAD_SPECS } from './taskTypePayloads'

export function CreateTaskModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const { push } = useToast()

  const [name, setName] = useState('')
  const [taskType, setTaskType] = useState<string>(TASK_TYPES[0])
  const [payload, setPayload] = useState<Record<string, unknown>>(
    defaultPayload(TASK_TYPES[0]),
  )
  const [priority, setPriority] = useState(0)
  const [maxRetries, setMaxRetries] = useState(3)
  const [scheduledAt, setScheduledAt] = useState('')

  const mutation = useMutation({
    mutationFn: createTask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      push('Task created', 'success')
      onClose()
    },
    onError: (err) => {
      push(err instanceof ApiError ? err.message : 'Failed to create task', 'error')
    },
  })

  function onTaskTypeChange(value: string) {
    setTaskType(value)
    setPayload(defaultPayload(value))
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    mutation.mutate({
      name,
      task_type: taskType,
      payload,
      priority,
      max_retries: maxRetries,
      scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : null,
    })
  }

  const spec = PAYLOAD_SPECS[taskType] ?? []

  return (
    <Modal
      title="New task"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            type="submit"
            form="create-task-form"
            disabled={mutation.isPending || !name.trim()}
          >
            {mutation.isPending ? 'Creating…' : 'Create task'}
          </Button>
        </>
      }
    >
      <form id="create-task-form" onSubmit={onSubmit} className="flex flex-col gap-4">
        <div>
          <Label htmlFor="task-name">Name</Label>
          <Input
            id="task-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Nightly report"
            required
          />
        </div>

        <div>
          <Label htmlFor="task-type">Task type</Label>
          <Select
            id="task-type"
            value={taskType}
            onChange={(e) => onTaskTypeChange(e.target.value)}
          >
            {TASK_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </Select>
        </div>

        {spec.length > 0 && (
          <div className="rounded-lg border border-border p-3">
            <p className="mb-3 text-xs font-medium uppercase tracking-wide text-ink-muted">
              Payload
            </p>
            <div className="flex flex-col gap-3">
              {spec.map((field) => (
                <div key={field.key}>
                  <Label htmlFor={`payload-${field.key}`}>{field.label}</Label>
                  {field.kind === 'boolean' ? (
                    <Select
                      id={`payload-${field.key}`}
                      value={String(payload[field.key])}
                      onChange={(e) =>
                        setPayload((p) => ({
                          ...p,
                          [field.key]: e.target.value === 'true',
                        }))
                      }
                    >
                      <option value="false">false</option>
                      <option value="true">true</option>
                    </Select>
                  ) : (
                    <Input
                      id={`payload-${field.key}`}
                      type={field.kind === 'number' ? 'number' : 'text'}
                      value={String(payload[field.key] ?? '')}
                      onChange={(e) =>
                        setPayload((p) => ({
                          ...p,
                          [field.key]:
                            field.kind === 'number'
                              ? Number(e.target.value)
                              : e.target.value,
                        }))
                      }
                    />
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-4">
          <div>
            <Label htmlFor="priority">Priority (0-9)</Label>
            <Input
              id="priority"
              type="number"
              min={0}
              max={9}
              value={priority}
              onChange={(e) =>
                setPriority(Math.max(0, Math.min(9, Number(e.target.value))))
              }
            />
          </div>
          <div>
            <Label htmlFor="max-retries">Max retries</Label>
            <Input
              id="max-retries"
              type="number"
              min={0}
              value={maxRetries}
              onChange={(e) => setMaxRetries(Math.max(0, Number(e.target.value)))}
            />
          </div>
        </div>

        <div>
          <Label htmlFor="scheduled-at">Run at (optional)</Label>
          <Input
            id="scheduled-at"
            type="datetime-local"
            value={scheduledAt}
            onChange={(e) => setScheduledAt(e.target.value)}
          />
        </div>
      </form>
    </Modal>
  )
}
