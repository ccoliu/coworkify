import { TASK_STATUSES, type TaskListFilters } from '../../lib/types'
import { useTaskTypeCatalog } from '../../lib/taskTypeCatalog'
import { Select } from '../../components/Field'

interface Props {
  filters: TaskListFilters
  onChange: (filters: TaskListFilters) => void
}

export function TaskFilters({ filters, onChange }: Props) {
  const { data: taskTypes } = useTaskTypeCatalog()

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Select
        className="w-auto"
        value={filters.status ?? ''}
        onChange={(e) =>
          onChange({ ...filters, status: e.target.value as TaskListFilters['status'], offset: 0 })
        }
      >
        <option value="">All statuses</option>
        {TASK_STATUSES.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </Select>

      <Select
        className="w-auto"
        value={filters.task_type ?? ''}
        onChange={(e) => onChange({ ...filters, task_type: e.target.value, offset: 0 })}
      >
        <option value="">All types</option>
        {(taskTypes ?? []).map((t) => (
          <option key={t.task_type} value={t.task_type}>
            {t.label}
          </option>
        ))}
      </Select>
    </div>
  )
}
