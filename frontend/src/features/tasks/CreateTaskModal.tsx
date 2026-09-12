import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import { ApiError, createTask } from '../../lib/apiClient'
import { defaultPayloadFor, useTaskTypeCatalog } from '../../lib/taskTypeCatalog'
import { Button } from '../../components/Button'
import { Input, Label, Select } from '../../components/Field'
import { Modal } from '../../components/Modal'
import { Spinner } from '../../components/Spinner'
import { useToast } from '../../context/ToastContext'
import { TaskPayloadFields } from './TaskPayloadFields'

export function CreateTaskModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const { data: taskTypes, isLoading: typesLoading } = useTaskTypeCatalog()

  const [name, setName] = useState('')
  const [taskType, setTaskType] = useState<string>('')
  const [payload, setPayload] = useState<Record<string, unknown>>({})
  const [priority, setPriority] = useState(0)
  const [maxRetries, setMaxRetries] = useState(3)
  const [scheduledAt, setScheduledAt] = useState('')

  // 目錄載入回來之前不知道第一個 task type 是什麼，載入後補上預設值
  useEffect(() => {
    if (taskTypes && taskTypes.length > 0 && !taskType) {
      setTaskType(taskTypes[0].task_type)
      setPayload(defaultPayloadFor(taskTypes[0]))
    }
  }, [taskTypes, taskType])

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
    setPayload(defaultPayloadFor(taskTypes?.find((t) => t.task_type === value)))
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

  const spec = taskTypes?.find((t) => t.task_type === taskType)

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
            disabled={mutation.isPending || !name.trim() || !taskType}
          >
            {mutation.isPending ? 'Creating…' : 'Create task'}
          </Button>
        </>
      }
    >
      {typesLoading ? (
        <div className="flex items-center justify-center py-8">
          <Spinner />
        </div>
      ) : (
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
            <Select id="task-type" value={taskType} onChange={(e) => onTaskTypeChange(e.target.value)}>
              {(taskTypes ?? []).map((t) => (
                <option key={t.task_type} value={t.task_type}>
                  {t.label}
                </option>
              ))}
            </Select>
            {spec?.description && <p className="mt-1 text-xs text-ink-muted">{spec.description}</p>}
          </div>

          {spec && spec.fields.length > 0 && (
            <div className="rounded-lg border border-border p-3">
              <p className="mb-3 text-xs font-medium uppercase tracking-wide text-ink-muted">Payload</p>
              <TaskPayloadFields
                idPrefix="payload"
                fields={spec.fields}
                payload={payload}
                onChange={setPayload}
              />
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
                onChange={(e) => setPriority(Math.max(0, Math.min(9, Number(e.target.value))))}
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
      )}
    </Modal>
  )
}
