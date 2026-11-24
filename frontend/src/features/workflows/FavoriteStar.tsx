import { useMutation, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { TbStar, TbStarFilled } from 'react-icons/tb'
import { ApiError, setDefinitionFavorite } from '../../lib/apiClient'
import { useToast } from '../../context/ToastContext'
import type { WorkflowDefinition } from '../../lib/types'

/** 標成常用：建構器的 Workflows 選單會先列出這些。 */
export function FavoriteStar({ definition, className }: { definition: WorkflowDefinition; className?: string }) {
    const queryClient = useQueryClient()
    const { push } = useToast()
    const on = definition.is_favorite

    const toggle = useMutation({
        mutationFn: () => setDefinitionFavorite(definition.id, !on),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['definitions'] })
            queryClient.invalidateQueries({ queryKey: ['definition', definition.id], exact: true })
        },
        onError: (err) => push(err instanceof ApiError ? err.message : 'Failed to update favorite', 'error'),
    })

    return (
        <button
            type="button"
            // 放在可點、可拖的項目裡面：別讓點星號順便觸發外層
            onClick={(e) => {
                e.stopPropagation()
                toggle.mutate()
            }}
            onMouseDown={(e) => e.stopPropagation()}
            draggable={false}
            disabled={toggle.isPending}
            aria-pressed={on}
            aria-label={on ? `Remove ${definition.name} from favorites` : `Add ${definition.name} to favorites`}
            title={on ? 'Remove from favorites' : 'Add to favorites — shows first when calling workflows from the builder'}
            className={clsx(
                'shrink-0 rounded p-0.5 transition-colors hover:bg-gridline disabled:opacity-50',
                on ? 'text-status-warning' : 'text-ink-secondary hover:text-status-warning',
                className,
            )}
        >
            {/* 圖示大小跟著字級走（1.15em）：DefinitionDetail 傳 text-lg 就會跟標題一樣大 */}
            {on ? <TbStarFilled size="1.15em" /> : <TbStar size="1.15em" />}
        </button>
    )
}
