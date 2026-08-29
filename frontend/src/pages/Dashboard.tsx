import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { listTasks } from '../lib/apiClient'
import type { TaskListFilters } from '../lib/types'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { Spinner } from '../components/Spinner'
import { CreateTaskModal } from '../features/tasks/CreateTaskModal'
import { TaskFilters } from '../features/tasks/TaskFilters'
import { TaskTable } from '../features/tasks/TaskTable'

const PAGE_SIZE = 20

export function Dashboard() {
  const [filters, setFilters] = useState<TaskListFilters>({
    status: '',
    task_type: '',
    limit: PAGE_SIZE,
    offset: 0,
  })
  const [showCreate, setShowCreate] = useState(false)

  const { data: tasks, isLoading, isError } = useQuery({
    queryKey: ['tasks', filters],
    queryFn: () => listTasks(filters),
  })

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-ink">Tasks</h1>
          <p className="text-sm text-ink-muted">
            Sorted by newest first, then priority. Live status updates arrive automatically.
          </p>
        </div>
        <Button variant="primary" onClick={() => setShowCreate(true)}>
          New task
        </Button>
      </div>

      <div className="flex items-center justify-between">
        <TaskFilters filters={filters} onChange={setFilters} />
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            disabled={filters.offset === 0}
            onClick={() =>
              setFilters((f) => ({ ...f, offset: Math.max(0, f.offset - PAGE_SIZE) }))
            }
          >
            Previous
          </Button>
          <Button
            variant="ghost"
            disabled={!tasks || tasks.length < PAGE_SIZE}
            onClick={() => setFilters((f) => ({ ...f, offset: f.offset + PAGE_SIZE }))}
          >
            Next
          </Button>
        </div>
      </div>

      <Card>
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Spinner />
          </div>
        ) : isError ? (
          <div className="px-6 py-16 text-center text-sm text-status-critical">
            Failed to load tasks.
          </div>
        ) : (
          <TaskTable tasks={tasks ?? []} />
        )}
      </Card>

      {showCreate && <CreateTaskModal onClose={() => setShowCreate(false)} />}
    </div>
  )
}
