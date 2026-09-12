import { useTaskTypeCatalog } from "../../lib/taskTypeCatalog";
import { Spinner } from "../../components/Spinner";
import { PythonIcon, WebIcon, BashIcon, SplitIcon, RobotIcon } from "../../components/Icon";

export const TASK_TYPE_DRAG_MIME = 'application/coworkify-task-type'

export function TaskTypePalette({ onAdd }: { onAdd: (taskType: string) => void }) {
    const { data: taskTypes, isLoading } = useTaskTypeCatalog()

    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-8">
                <Spinner />
            </div>
        )
    }

    return (
        <div className="flex flex-col gap-2 p-3">
            <p className="px-1 text-xs uppercase tracking-wide text-ink-muted">Task types</p>
            {(taskTypes ?? []).map((t) => (
                <button
                    key={t.task_type}
                    type="button"
                    draggable
                    onDragStart={(e) => {
                        e.dataTransfer.setData(TASK_TYPE_DRAG_MIME, t.task_type)
                        e.dataTransfer.effectAllowed = 'move'
                    }}
                    onClick={() => onAdd(t.task_type)}
                    className="cursor-grab rounded-lg border border-border bg-surface px-3 py-2 text-left hover:border-accent active:cursor-grabbing"
                    title={t.description}
                >
                    <div className="flex items-center gap-2">
                        {t.task_type === 'python' && <PythonIcon />}
                        {t.task_type === 'http_request' && <WebIcon />}
                        {t.task_type === 'shell' && <BashIcon />}
                        {t.task_type === 'condition' && <SplitIcon />}
                        {t.task_type === 'agent_step' && <RobotIcon />}
                        <span className="block text-sm font-medium text-ink">{t.label}</span>
                    </div>
                    <span className="block truncate font-mono text-xs text-ink-muted">{t.task_type}</span>
                </button>
            ))}
            <p className="px-1 pt-1 text-xs text-ink-muted">拖進畫布，或點一下加到中央</p>
        </div>
    )
}