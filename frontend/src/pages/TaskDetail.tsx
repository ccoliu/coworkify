import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError, deleteTask, getTask } from '../lib/apiClient'
import { formatDateTime } from '../lib/format'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { EmptyState } from '../components/EmptyState'
import { Spinner } from '../components/Spinner'
import { StatusBadge } from '../components/StatusBadge'
import { useWs } from '../context/WsContext'
import { useToast } from '../context/ToastContext'

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-ink-muted">{label}</dt>
      <dd className="mt-0.5 text-sm text-ink">{value}</dd>
    </div>
  )
}

export function TaskDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { push } = useToast()
  const { events } = useWs()

  const {
    data: task,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['task', id],
    queryFn: () => getTask(id as string),
    enabled: !!id,
  })

  const remove = useMutation({
    mutationFn: deleteTask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      push('Task deleted', 'success')
      navigate('/')
    },
    onError: (err) => {
      push(err instanceof ApiError ? err.message : 'Failed to delete task', 'error')
    },
  })

  const timeline = events.filter((e) => e.task_id === id)

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner />
      </div>
    )
  }

  if (isError || !task) {
    return (
      <EmptyState
        title="Task not found"
        description="It may have been deleted."
        action={
          <Link to="/" className="text-sm font-medium text-accent">
            Back to tasks
          </Link>
        }
      />
    )
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between">
        <div>
          <Link to="/" className="text-sm text-ink-muted hover:text-ink">
            ← Tasks
          </Link>
          <h1 className="mt-1 text-lg font-semibold text-ink">{task.name}</h1>
          <div className="mt-1 font-mono text-xs text-ink-muted">{task.id}</div>
        </div>
        <Button
          variant="danger"
          onClick={() => {
            if (confirm(`Delete task "${task.name}"?`)) remove.mutate(task.id)
          }}
        >
          Delete
        </Button>
      </div>

      <Card className="p-5">
        <dl className="grid grid-cols-2 gap-5 sm:grid-cols-4">
          <Field label="Status" value={<StatusBadge status={task.status} />} />
          <Field label="Type" value={task.task_type} />
          <Field label="Priority" value={task.priority} />
          <Field
            label="Retries"
            value={`${task.retry_count} / ${task.max_retries}`}
          />
          <Field label="Created" value={formatDateTime(task.created_at)} />
          <Field label="Updated" value={formatDateTime(task.updated_at)} />
          <Field
            label="Scheduled at"
            value={task.scheduled_at ? formatDateTime(task.scheduled_at) : '—'}
          />
        </dl>
      </Card>

      <Card className="p-5">
        <h2 className="mb-3 text-sm font-semibold text-ink">Payload</h2>
        <pre className="overflow-x-auto rounded-lg bg-plane p-3 font-mono text-xs text-ink-secondary">
          {JSON.stringify(task.payload, null, 2)}
        </pre>
      </Card>

      <Card className="p-5">
        <h2 className="mb-3 text-sm font-semibold text-ink">Live activity</h2>
        {timeline.length === 0 ? (
          <p className="text-sm text-ink-muted">
            No live events observed yet for this task in this session.
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {timeline.map((event, i) => (
              <li key={i} className="flex items-start gap-3 text-sm">
                <StatusBadge status={event.status} />
                <div className="min-w-0 flex-1">
                  <div className="text-xs text-ink-muted">
                    {new Date(event.timestamp * 1000).toLocaleTimeString()}
                  </div>
                  {event.error && (
                    <div className="mt-0.5 text-xs text-status-critical">{event.error}</div>
                  )}
                  {event.result != null && (
                    <pre className="mt-1 overflow-x-auto rounded bg-plane p-2 font-mono text-xs text-ink-secondary">
                      {JSON.stringify(event.result, null, 2)}
                    </pre>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
