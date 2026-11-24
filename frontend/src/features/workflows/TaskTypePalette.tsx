import { useTaskTypeCatalog } from "../../lib/taskTypeCatalog";
import { Spinner } from "../../components/Spinner";
import { getIcon } from "../../components/Icon";
import type { WorkflowDefinition } from "../../lib/types";
import { FavoriteStar } from "./FavoriteStar";
import { SUBWORKFLOW, WORKFLOW_DRAG_MIME } from "./subworkflow";

export const TASK_TYPE_DRAG_MIME = 'application/coworkify-task-type'

const ITEM_CLASS =
    'cursor-grab rounded-lg border border-border bg-surface px-3 py-2 text-left hover:border-accent active:cursor-grabbing'

/** 左側 Workflows 區塊要的資料。favorites 一開始就有；others 要按了 Show all 才載入。 */
export interface WorkflowPaletteProps {
    favorites: WorkflowDefinition[]
    others: WorkflowDefinition[] | undefined
    othersLoading: boolean
    showOthers: boolean
    onShowOthers: () => void
    onAdd: (definitionId: string) => void
}

function WorkflowItem({ definition, onAdd }: { definition: WorkflowDefinition; onAdd: (id: string) => void }) {
    return (
        // 裡面有星號按鈕，外層不能也是 <button>，改用 div + role
        <div
            role="button"
            tabIndex={0}
            draggable
            onDragStart={(e) => {
                e.dataTransfer.setData(WORKFLOW_DRAG_MIME, definition.id)
                e.dataTransfer.effectAllowed = 'move'
            }}
            onClick={() => onAdd(definition.id)}
            onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onAdd(definition.id)
                }
            }}
            className={ITEM_CLASS}
            title={definition.description ?? `Run ${definition.name} as a step and wait for it to finish`}
        >
            <div className="flex items-center gap-2">
                {getIcon(SUBWORKFLOW)}
                <span className="block min-w-0 flex-1 truncate text-sm font-medium text-ink">{definition.name}</span>
                <FavoriteStar definition={definition} />
            </div>
            <span className="block truncate font-mono text-xs text-ink-muted">
                {definition.input_schema.length > 0
                    ? `inputs: ${definition.input_schema.map((f) => f.key).join(', ')}`
                    : 'no inputs'}
            </span>
        </div>
    )
}

function WorkflowSection({ favorites, others, othersLoading, showOthers, onShowOthers, onAdd }: WorkflowPaletteProps) {
    return (
        <>
            <p className="mt-2 px-1 text-xs uppercase tracking-wide text-ink-muted">Workflows</p>
            {favorites.length === 0 && (
                <p className="px-1 text-xs text-ink-muted">
                    點 workflow 旁的 ☆ 標成常用，它就會固定出現在這裡。
                </p>
            )}
            {favorites.map((d) => (
                <WorkflowItem key={d.id} definition={d} onAdd={onAdd} />
            ))}

            {!showOthers ? (
                <button
                    type="button"
                    onClick={onShowOthers}
                    className="rounded-lg border border-dashed border-border px-3 py-1.5 text-xs font-medium text-ink-secondary hover:border-accent hover:text-accent"
                >
                    Show other workflows
                </button>
            ) : othersLoading ? (
                <div className="flex justify-center py-2">
                    <Spinner />
                </div>
            ) : (
                <>
                    <p className="mt-1 px-1 text-xs text-ink-muted">
                        {(others ?? []).length > 0 ? 'Others' : '沒有其他 workflow 了'}
                    </p>
                    {(others ?? []).map((d) => (
                        <WorkflowItem key={d.id} definition={d} onAdd={onAdd} />
                    ))}
                </>
            )}
        </>
    )
}

export function TaskTypePalette({ onAdd, workflows }: { onAdd: (taskType: string) => void; workflows?: WorkflowPaletteProps }) {
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
                    className={ITEM_CLASS}
                    title={t.description}
                >
                    <div className="flex items-center gap-2">
                        {getIcon(t.task_type)}
                        <span className="block text-sm font-medium text-ink">{t.label}</span>
                    </div>
                    <span className="block truncate font-mono text-xs text-ink-muted">{t.task_type}</span>
                </button>
            ))}

            {workflows && <WorkflowSection {...workflows} />}

            <p className="px-1 pt-1 text-xs text-ink-muted">拖進畫布，或點一下加到中央</p>
        </div>
    )
}
