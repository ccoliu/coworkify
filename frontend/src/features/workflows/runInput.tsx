import type { TaskFieldSpec } from '../../lib/types'
import { TaskPayloadFields } from '../tasks/TaskPayloadFields'

/** run 表單的初始值：有 default 用 default，select 沒 default 就先選第一個，免得畫面顯示第一項但值是 null。 */
export function initialInput(schema: TaskFieldSpec[]): Record<string, unknown> {
    return Object.fromEntries(
        schema.map((f) => {
            if (f.default != null && f.default !== undefined) return [f.key, f.default]
            if (f.kind === "select") return [f.key, f.options?.[0]?.value ?? null]
            if (f.kind === "multiselect") return [f.key, []]
            if (f.kind === "boolean") return [f.key, false]
            return [f.key, null]
        })
    )
}

/** 後端才是權威，這裡只是為了讓送出按鈕先擋住、把缺的欄位名字列出來。 */
export function missingRequired(schema: TaskFieldSpec[], input: Record<string, unknown>): string[] {
    return schema
        .filter((f) => {
            const v = input[f.key]
            return f.required && (v == null || v === '' || (Array.isArray(v) && v.length === 0))
        })
        .map((f) => f.label)
}

export function RunInputFields({
    idPrefix,
    schema,
    values,
    onChange,
    emptyHint = '這個 workflow 沒有宣告輸入欄位，會用各步驟裡寫死的設定執行。'
}: {
    idPrefix: string,
    schema: TaskFieldSpec[],
    values: Record<string, unknown>,
    onChange: (next: Record<string, unknown>) => void,
    emptyHint?: string,
}) {
    if (schema.length === 0) return <p className="text-sm text-ink-muted">{emptyHint}</p>
    return <TaskPayloadFields idPrefix={idPrefix} fields={schema} payload={values} onChange={onChange} />
}