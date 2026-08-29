import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ApiError, deleteTask } from '../../lib/apiClient'
import { formatRelativeTime, shortId } from '../../lib/format'
import type { Task } from '../../lib/types'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { StatusBadge } from '../../components/StatusBadge'
import { useToast } from '../../context/ToastContext'

export function TaskTable({ tasks }: { tasks: Task[] }) {
  const queryClient = useQueryClient()
  const { push } = useToast()

  const remove = useMutation({
    mutationFn: deleteTask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
      push('Task deleted', 'success')
    },
    onError: (err) => {
      push(err instanceof ApiError ? err.message : 'Failed to delete task', 'error')
    },
  })

  if (tasks.length === 0) {
    return (
      <EmptyState
        title="No tasks match these filters"
        description="Try clearing a filter, or create a new task to get started."
      />
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-ink-muted">
            <th className="px-4 py-2.5 font-medium">Name</th>
            <th className="px-4 py-2.5 font-medium">Type</th>
            <th className="px-4 py-2.5 font-medium">Status</th>
            <th className="px-4 py-2.5 font-medium">Priority</th>
            <th className="px-4 py-2.5 font-medium">Retries</th>
            <th className="px-4 py-2.5 font-medium">Updated</th>
            <th className="px-4 py-2.5" />
          </tr>
        </thead>
        <tbody>
          {tasks.map((task) => (
            <tr
              key={task.id}
              className="border-b border-border last:border-0 hover:bg-surface"
            >
              <td className="px-4 py-3">
                <Link
                  to={`/tasks/${task.id}`}
                  className="font-medium text-ink hover:text-accent"
                >
                  {task.name}
                </Link>
                <div className="font-mono text-xs text-ink-muted">
                  {shortId(task.id)}
                </div>
              </td>
              <td className="px-4 py-3 text-ink-secondary">{task.task_type}</td>
              <td className="px-4 py-3">
                <StatusBadge status={task.status} />
              </td>
              <td className="px-4 py-3 text-ink-secondary">{task.priority}</td>
              <td className="px-4 py-3 text-ink-secondary">
                {task.retry_count}/{task.max_retries}
              </td>
              <td className="px-4 py-3 text-ink-muted">
                {formatRelativeTime(task.updated_at)}
              </td>
              <td className="px-4 py-3 text-right">
                <Button
                  variant="ghost"
                  onClick={() => {
                    if (confirm(`Delete task "${task.name}"?`)) remove.mutate(task.id)
                  }}
                >
                  Delete
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
