import type { TaskFieldKind, TaskFieldOption, TaskFieldSpec } from "../../lib/types";
import { Button } from "../../components/Button";
import { Input, Label, Select } from "../../components/Field";

const KINDS: { value: TaskFieldKind; label: string }[] = [
    { value: 'string', label: '單行文字' },
    { value: 'text', label: '多行文字' },
    { value: 'number', label: '數字' },
    { value: 'boolean', label: 'true / false' },
    { value: 'select', label: '單選' },
    { value: 'multiselect', label: '多選' },
]

export function emptyInputField(taken: Set<string>): TaskFieldSpec {
    let i = 1
    while (taken.has(`field_${i}`)) i += 1
    return { key: `field_${i}`, label: '', kind: 'string', default: null, required: false, help: null, options: null }
}

const optionsToText = (options: TaskFieldOption[] | null | undefined) =>
    (options ?? []).map((o) => o.value).join(', ')

/** 逗號分隔的值清單；label 就用值本身，這個編輯器不另外提供顯示名稱 */
const textToOptions = (text: string): TaskFieldOption[] | null => {
    const values = text.split(',').map((s) => s.trim()).filter(Boolean)
    return values.length > 0 ? values.map((v) => ({ value: v, label: v })) : null
}

function DefaultValueField({
    field,
    id,
    onChange,
}: {
    field: TaskFieldSpec,
    id: string,
    onChange: (value: TaskFieldSpec['default']) => void
}) {
    if (field.kind === 'boolean') {
        return (
            <Select id={id} value={String(field.default === true)} onChange={(e) => onChange(e.target.value === 'true')}>
                <option value="false">false</option>
                <option value="true">true</option>
            </Select>
        )
    }
    if (field.kind === 'select') {
        return (
            <Select id={id} value={String(field.default ?? '')} onChange={(e) => onChange(e.target.value || null)}>
                <option value="">— 沒有預設 —</option>
                {(field.options ?? []).map((o) => (
                    <option key={o.value} value={o.value}>
                        {o.label}
                    </option>
                ))}
            </Select>
        )
    }
    if (field.kind === 'multiselect') {
        return (
            <Input
                id={id}
                value={Array.isArray(field.default) ? field.default.join(', ') : ''}
                onChange={(e) => onChange(textToOptions(e.target.value)?.map((o) => o.value) ?? [])}
                placeholder="逗號分隔"
            />
        )
    }
    return (
        <Input
            id={id}
            type={field.kind === 'number' ? 'number' : 'text'}
            value={field.default == null ? '' : String(field.default)}
            onChange={(e) => {
                const raw = e.target.value
                if (raw === '') return onChange(null)
                onChange(field.kind === 'number' ? Number(raw) : raw)
            }}
        />
    )
}

/**
 * 定義的 input_schema 編輯器。產出的形狀跟 GET /tasks/types 的 field spec 相同，
 * 所以 run 表單可以直接餵給 TaskPayloadFields。
 */
export function InputSchemaEditor({
    schema,
    onChange
}: {
    schema: TaskFieldSpec[],
    onChange: (next: TaskFieldSpec[]) => void
}) {
    const update = (index: number, patch: Partial<TaskFieldSpec>) => {
        onChange(schema.map((f, i) => (i === index ? { ...f, ...patch } : f)))
    }

    const move = (index: number, delta: number) => {
        const target = index + delta
        if (target < 0 || target >= schema.length) return
        const next = [...schema]
            ;[next[index], next[target]] = [next[target], next[index]]
        onChange(next)
    }

    return (
        <div className="flex flex-col gap-3">
            {schema.length === 0 && (
                <p className="text-sm text-ink-muted">
                    還沒有輸入欄位。加了之後，每次執行這條 workflow 都會先填這張表單，值會從 input step 進入，
                    下游用 <code className="font-mono">{'{{steps.<input step 的 key>.result.<欄位 key>}}'}</code> 取用
                    （python 步驟則直接用 <code className="font-mono">inputs</code>）。
                </p>
            )}

            {schema.map((field, i) => {
                const id = `input-field-${i}`
                return (
                    <div key={i} className="rounded-lg border border-border p-3">
                        <div className="mb-3 flex items-center justify-between">
                            <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
                                Field {i + 1}
                            </p>
                            <div className="flex items-center gap-1">
                                <button
                                    type="button"
                                    onClick={() => move(i, -1)}
                                    disabled={i === 0}
                                    className="px-1.5 text-xs text-ink-muted hover:text-ink disabled:opacity-40"
                                >
                                    ↑
                                </button>
                                <button
                                    type="button"
                                    onClick={() => move(i, 1)}
                                    disabled={i === schema.length - 1}
                                    className="px-1.5 text-xs text-ink-muted hover:text-ink disabled:opacity-40"
                                >
                                    ↓
                                </button>
                                <button
                                    type="button"
                                    onClick={() => onChange(schema.filter((_, j) => j !== i))}
                                    className="ml-1 text-xs font-medium text-ink-muted hover:text-status-critical"
                                >
                                    Remove
                                </button>
                            </div>
                        </div>

                        <div className="grid gap-3 sm:grid-cols-2">
                            <div>
                                <Label htmlFor={`${id}-key`}>Key</Label>
                                <Input
                                    id={`${id}-key`}
                                    value={field.key}
                                    onChange={(e) => update(i, { key: e.target.value })}
                                    className="font-mono"
                                    placeholder="keyword"
                                />
                            </div>
                            <div>
                                <Label htmlFor={`${id}-label`}>Label</Label>
                                <Input
                                    id={`${id}-label`}
                                    value={field.label}
                                    onChange={(e) => update(i, { label: e.target.value })}
                                    placeholder="搜尋關鍵字"
                                />
                            </div>
                            <div>
                                <Label htmlFor={`${id}-kind`}>Type</Label>
                                <Select
                                    id={`${id}-kind`}
                                    value={field.kind}
                                    onChange={(e) =>
                                        // 換型別之後舊的預設值與選項多半不再合法，一起清掉
                                        update(i, {
                                            kind: e.target.value as TaskFieldKind,
                                            default: null,
                                            options: null,
                                        })
                                    }
                                >
                                    {KINDS.map((k) => (
                                        <option key={k.value} value={k.value}>
                                            {k.label}
                                        </option>
                                    ))}
                                </Select>
                            </div>
                            <div>
                                <Label htmlFor={`${id}-default`}>Default</Label>
                                <DefaultValueField
                                    field={field}
                                    id={`${id}-default`}
                                    onChange={(value) => update(i, { default: value })}
                                />
                            </div>

                            {(field.kind === 'select' || field.kind === 'multiselect') && (
                                <div className="sm:col-span-2">
                                    <Label htmlFor={`${id}-options`}>Options</Label>
                                    <Input
                                        id={`${id}-options`}
                                        value={optionsToText(field.options)}
                                        onChange={(e) => update(i, { options: textToOptions(e.target.value) })}
                                        placeholder="backend, frontend, devops"
                                    />
                                </div>
                            )}

                            <div className="sm:col-span-2">
                                <Label htmlFor={`${id}-help`}>Help text</Label>
                                <Input
                                    id={`${id}-help`}
                                    value={field.help ?? ''}
                                    onChange={(e) => update(i, { help: e.target.value || null })}
                                    placeholder="選填，顯示在欄位下方"
                                />
                            </div>

                            <label className="flex items-center gap-1.5 text-sm text-ink-secondary">
                                <input
                                    type="checkbox"
                                    checked={field.required}
                                    onChange={(e) => update(i, { required: e.target.checked })}
                                />
                                必填
                            </label>
                        </div>
                    </div>
                )
            })}

            <div>
                <Button
                    type="button"
                    variant="secondary"
                    onClick={() => onChange([...schema, emptyInputField(new Set(schema.map((f) => f.key)))])}
                >
                    + Add input field
                </Button>
            </div>
        </div>
    )
}