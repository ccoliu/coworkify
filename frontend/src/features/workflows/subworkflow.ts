import { useQuery } from '@tanstack/react-query'
import { getDefinition, listDefinitions } from '../../lib/apiClient'
import type { WorkflowDefinition } from '../../lib/types'

/** 把另一條 workflow 定義當成一個步驟來跑（後端 app/tasks/subworkflow.py）。不在 task-type 目錄裡。 */
export const SUBWORKFLOW = 'subworkflow'

export const WORKFLOW_DRAG_MIME = 'application/coworkify-workflow'

// 都掛在 ['definitions'] 底下：存檔、刪除、標星號時 invalidate ['definitions'] 會一起更新
/** 標成常用的定義：建構器一打開就載入。 */
export function useFavoriteDefinitions() {
    return useQuery({
        queryKey: ['definitions', 'favorites'],
        queryFn: () => listDefinitions(100, 0, true),
    })
}

/** 其他定義：使用者按了「Show all」才去抓。 */
export function useOtherDefinitions(enabled: boolean) {
    return useQuery({
        queryKey: ['definitions', 'others'],
        queryFn: () => listDefinitions(100, 0, false),
        enabled,
    })
}

/** 單一條定義（subworkflow 步驟要知道它的輸入欄位）。跟定義詳細頁共用 query key。 */
export function useDefinition(id: string | null) {
    return useQuery({
        queryKey: ['definition', id],
        queryFn: () => getDefinition(id as string),
        enabled: id != null,
        retry: false, // 404 代表被刪了，不用重試
    })
}

/** 新的 subworkflow 步驟的 payload：要呼叫哪條定義，加上它每個輸入欄位的預設值。 */
export function subworkflowPayloadFor(definition: WorkflowDefinition): Record<string, unknown> {
    return {
        definition_id: definition.id,
        ...Object.fromEntries(definition.input_schema.map((f) => [f.key, f.default])),
    }
}

export function calledDefinitionId(payload: Record<string, unknown>): string | null {
    const id = payload.definition_id
    return typeof id === 'string' && id !== '' ? id : null
}
