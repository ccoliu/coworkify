import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { useState, type FormEvent } from 'react'
import { ApiError, createTrigger, listDefinitions, updateTrigger } from '../../lib/apiClient'
import type { TriggerKind, TriggerOnStatus, WorkflowTrigger, WorkflowTriggerWithSecret } from '../../lib/types'
import { Button } from '../../components/Button'
import { Input, Label, Select } from '../../components/Field'
import { Modal } from '../../components/Modal'
import { Spinner } from '../../components/Spinner'
import { useToast } from '../../context/ToastContext'

interface FilterRow {
    path: string
    value: string
}

const KIND_OPTIONS: { value: TriggerKind; label: string; hint: string }[] = [
    { value: 'webhook', label: 'Webhook', hint: 'GitHub 或自己的腳本打一個網址' },
    { value: 'workflow', label: 'After another workflow', hint: '另一條 workflow 的 run 結束時' },
]

const ON_STATUS_LABELS: Record<TriggerOnStatus, string> = {
    success: 'succeeds',
    failed: 'fails',
    any: 'finishes (either way)',
}

/**
 * filter 的期望值在畫面上是一段文字，規則跟 wait_for 的 expected 一樣：
 * 一般文字就是字串；以 [ 開頭才當 JSON 陣列解析（代表「其中之一」）。
 * 要比對數字或布林就寫成 [200]、[true]——不然 "200" 會被悄悄變成數字。
 */
function filterValueToText(value: unknown): string {
    if (typeof value === 'string') return value
    return JSON.stringify(Array.isArray(value) ? value : [value])
}

function parseFilterValue(text: string): unknown {
    const trimmed = text.trim()
    if (!trimmed.startsWith('[')) return text
    const parsed: unknown = JSON.parse(trimmed)
    if (!Array.isArray(parsed)) throw new Error('not an array')
    return parsed
}

function filterRowsFrom(filter: Record<string, unknown> | undefined): FilterRow[] {
    const rows = Object.entries(filter ?? {}).map(([path, value]) => ({ path, value: filterValueToText(value) }))
    return rows.length ? rows : [{ path: '', value: '' }]
}

export function TriggerFormModal({
    trigger,
    onClose,
    onCreated,
}: {
    // null = 新增
    trigger: WorkflowTrigger | null
    onClose: () => void
    // 建立成功後把結果交出去；webhook 帶著 secret，由外層顯示一次
    onCreated: (created: WorkflowTriggerWithSecret) => void
}) {
    const queryClient = useQueryClient()
    const { push } = useToast()

    const { data: definitions, isLoading } = useQuery({
        queryKey: ['definitions'],
        queryFn: () => listDefinitions(100),
    })

    const [kind, setKind] = useState<TriggerKind>(trigger?.kind ?? 'webhook')
    const [name, setName] = useState(trigger?.name ?? '')
    const [definitionId, setDefinitionId] = useState(trigger?.definition_id ?? '')
    const [sourceId, setSourceId] = useState(trigger?.source_definition_id ?? '')
    const [onStatus, setOnStatus] = useState<TriggerOnStatus>(trigger?.on_status ?? 'success')
    const [mapping, setMapping] = useState<Record<string, string>>(trigger?.input_mapping ?? {})
    const [filterRows, setFilterRows] = useState<FilterRow[]>(() => filterRowsFrom(trigger?.filter))

    const isWorkflow = kind === 'workflow'
    const definition = definitions?.find((d) => d.id === definitionId) ?? null
    const source = definitions?.find((d) => d.id === sourceId) ?? null
    const schema = definition?.input_schema ?? []
    const pathPlaceholder = isWorkflow ? 'result.summarize' : 'repository.full_name'

    // 只送目前 schema 裡有、而且有填路徑的欄位
    const cleanMapping = Object.fromEntries(
        schema.map((f) => [f.key, (mapping[f.key] ?? '').trim()] as const).filter(([, path]) => path),
    )
    const unmappedRequired = schema.filter((f) => f.required && f.default == null && !cleanMapping[f.key])

    const filterErrors: string[] = []
    const cleanFilter: Record<string, unknown> = {}
    for (const row of filterRows) {
        const path = row.path.trim()
        if (!path && !row.value.trim()) continue
        if (!path) {
            filterErrors.push('每個條件都要有路徑')
            continue
        }
        try {
            cleanFilter[path] = parseFilterValue(row.value)
        } catch {
            filterErrors.push(`${path}：以 [ 開頭的值必須是合法的 JSON 陣列`)
        }
    }

    const mutation = useMutation({
        mutationFn: async () => {
            if (trigger) {
                await updateTrigger(trigger.id, {
                    name,
                    input_mapping: cleanMapping,
                    filter: cleanFilter,
                    ...(trigger.kind === 'workflow' ? { on_status: onStatus } : {}),
                })
                return null
            }
            return createTrigger({
                name,
                kind,
                definition_id: definitionId,
                input_mapping: cleanMapping,
                filter: cleanFilter,
                ...(isWorkflow ? { source_definition_id: sourceId, on_status: onStatus } : {}),
            })
        },
        onSuccess: (created) => {
            queryClient.invalidateQueries({ queryKey: ['triggers'] })
            if (created) {
                onCreated(created)
            } else {
                push('Trigger updated', 'success')
                onClose()
            }
        },
        onError: (err) => push(err instanceof ApiError ? err.message : 'Failed to save trigger', 'error'),
    })

    function onSubmit(e: FormEvent) {
        e.preventDefault()
        mutation.mutate()
    }

    const canSubmit =
        name.trim() && definitionId && (!isWorkflow || (sourceId && sourceId !== definitionId)) && filterErrors.length === 0

    function setFilterRow(index: number, patch: Partial<FilterRow>) {
        setFilterRows((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)))
    }

    return (
        <Modal
            title={trigger ? `Edit ${trigger.name}` : 'New trigger'}
            onClose={onClose}
            footer={
                <>
                    <Button variant="ghost" onClick={onClose}>
                        Cancel
                    </Button>
                    <Button variant="primary" type="submit" form="trigger-form" disabled={mutation.isPending || !canSubmit}>
                        {mutation.isPending ? 'Saving…' : trigger ? 'Save' : 'Create trigger'}
                    </Button>
                </>
            }
        >
            {isLoading ? (
                <div className="flex items-center justify-center py-10">
                    <Spinner />
                </div>
            ) : (
                <form id="trigger-form" onSubmit={onSubmit} className="flex flex-col gap-4">
                    {/* 種類建好就不能改：兩種的設定（secret、來源產線）完全不同 */}
                    {!trigger && (
                        <div>
                            <Label>Starts when</Label>
                            <div className="grid grid-cols-2 gap-2">
                                {KIND_OPTIONS.map((option) => (
                                    <button
                                        key={option.value}
                                        type="button"
                                        onClick={() => {
                                            setKind(option.value)
                                            // 兩種的路徑取值對象不同，舊的對應和 filter 不能沿用
                                            setMapping({})
                                            setFilterRows([{ path: '', value: '' }])
                                        }}
                                        className={clsx(
                                            'rounded-lg border px-3 py-2 text-left transition-colors',
                                            kind === option.value
                                                ? 'border-accent bg-accent/10'
                                                : 'border-border hover:bg-plane',
                                        )}
                                    >
                                        <div className="text-sm font-medium text-ink">{option.label}</div>
                                        <div className="text-xs text-ink-muted">{option.hint}</div>
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {isWorkflow && (
                        <div className="grid grid-cols-[1fr_auto] items-end gap-2">
                            <div>
                                <Label htmlFor="trigger-source">When a run of</Label>
                                <Select
                                    id="trigger-source"
                                    value={sourceId}
                                    disabled={trigger !== null}
                                    onChange={(e) => setSourceId(e.target.value)}
                                    required
                                >
                                    <option value="">— pick a workflow —</option>
                                    {(definitions ?? []).map((d) => (
                                        <option key={d.id} value={d.id}>
                                            {d.name}
                                        </option>
                                    ))}
                                </Select>
                            </div>
                            <div>
                                <Select
                                    aria-label="Outcome"
                                    value={onStatus}
                                    onChange={(e) => setOnStatus(e.target.value as TriggerOnStatus)}
                                >
                                    {(Object.keys(ON_STATUS_LABELS) as TriggerOnStatus[]).map((s) => (
                                        <option key={s} value={s}>
                                            {ON_STATUS_LABELS[s]}
                                        </option>
                                    ))}
                                </Select>
                            </div>
                        </div>
                    )}

                    <div>
                        <Label htmlFor="trigger-definition">{isWorkflow ? 'Start this workflow' : 'Workflow'}</Label>
                        <Select
                            id="trigger-definition"
                            value={definitionId}
                            // 觸發器建好之後不能換產線：輸入對應是照那條產線的欄位設定的
                            disabled={trigger !== null}
                            onChange={(e) => {
                                setDefinitionId(e.target.value)
                                setMapping({})
                                const picked = definitions?.find((d) => d.id === e.target.value)
                                if (picked && !name.trim()) setName(isWorkflow ? `then ${picked.name}` : `${picked.name} webhook`)
                            }}
                            required
                        >
                            <option value="">— pick a workflow —</option>
                            {(definitions ?? []).map((d) => (
                                <option key={d.id} value={d.id}>
                                    {d.name} (v{d.version})
                                </option>
                            ))}
                        </Select>
                        {isWorkflow && sourceId && sourceId === definitionId && (
                            <p className="mt-1 text-xs text-status-critical">不能讓一條 workflow 觸發自己。</p>
                        )}
                    </div>

                    <div>
                        <Label htmlFor="trigger-name">Name</Label>
                        <Input
                            id="trigger-name"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder={isWorkflow ? 'post-summary-after-triage' : 'github-issue-opened'}
                            required
                        />
                    </div>

                    {definition && (
                        <div className="flex flex-col gap-3 border-t border-border pt-4">
                            <div>
                                <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">Input mapping</p>
                                {isWorkflow ? (
                                    <p className="mt-1 text-xs text-ink-muted">
                                        每個輸入欄位要從上游 run 的哪裡取值：<code className="font-mono">result.&lt;step key&gt;</code>{' '}
                                        是終端步驟的結果，<code className="font-mono">input.&lt;欄位&gt;</code> 是上游的輸入，
                                        還有 <code className="font-mono">status</code>、<code className="font-mono">workflow_id</code>。
                                        {source && (
                                            <>
                                                {' '}
                                                {source.name} 的步驟：
                                                {source.steps.map((s, i) => (
                                                    <span key={s.key}>
                                                        {i > 0 && '、'}
                                                        <code className="font-mono">{s.key}</code>
                                                    </span>
                                                ))}
                                                。
                                            </>
                                        )}
                                    </p>
                                ) : (
                                    <p className="mt-1 text-xs text-ink-muted">
                                        每個輸入欄位要從 request body 的哪裡取值，用點分隔，例如{' '}
                                        <code className="font-mono">repository.full_name</code>、
                                        <code className="font-mono">commits.0.id</code>。留空就用欄位的預設值。
                                        body 的其他內容不會進到 run。
                                    </p>
                                )}
                            </div>
                            {schema.length === 0 ? (
                                <p className="text-xs text-ink-muted">
                                    這個 workflow 沒有宣告輸入欄位，每次觸發都會用各步驟裡寫死的設定。
                                </p>
                            ) : (
                                schema.map((field) => (
                                    <div key={field.key} className="grid grid-cols-[10rem_1fr] items-center gap-3">
                                        <label htmlFor={`mapping-${field.key}`} className="text-sm text-ink-secondary">
                                            {field.label}
                                            {field.required && <span className="text-status-critical"> *</span>}
                                            <div className="font-mono text-xs text-ink-muted">{field.key}</div>
                                        </label>
                                        <Input
                                            id={`mapping-${field.key}`}
                                            className="font-mono"
                                            value={mapping[field.key] ?? ''}
                                            placeholder={pathPlaceholder}
                                            onChange={(e) => setMapping((m) => ({ ...m, [field.key]: e.target.value }))}
                                        />
                                    </div>
                                ))
                            )}
                            {unmappedRequired.length > 0 && (
                                <p className="text-xs text-status-warning">
                                    必填但沒有對應：{unmappedRequired.map((f) => f.label).join('、')}。
                                    {isWorkflow
                                        ? '觸發時會因為缺值而建不出 run，錯誤會記在這個觸發器上。'
                                        : 'webhook 進來時會因為缺值被拒絕（422）。'}
                                </p>
                            )}
                        </div>
                    )}

                    <div className="flex flex-col gap-3 border-t border-border pt-4">
                        <div>
                            <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">Filter (optional)</p>
                            <p className="mt-1 text-xs text-ink-muted">
                                所有條件都符合才建立 run。值是一般文字就比對字串；寫成 JSON 陣列代表「其中之一」，例如{' '}
                                <code className="font-mono">["opened","reopened"]</code>，比對數字或布林也要用陣列：
                                <code className="font-mono">[200]</code>。
                            </p>
                        </div>
                        {filterRows.map((row, index) => (
                            <div key={index} className="grid grid-cols-[1fr_1fr_auto] items-center gap-2">
                                <Input
                                    aria-label="Path"
                                    className="font-mono"
                                    value={row.path}
                                    placeholder={isWorkflow ? 'result.triage.severity' : 'action'}
                                    onChange={(e) => setFilterRow(index, { path: e.target.value })}
                                />
                                <Input
                                    aria-label="Expected value"
                                    className="font-mono"
                                    value={row.value}
                                    placeholder={isWorkflow ? 'high' : 'opened'}
                                    onChange={(e) => setFilterRow(index, { value: e.target.value })}
                                />
                                <Button
                                    variant="ghost"
                                    aria-label="Remove condition"
                                    onClick={() =>
                                        setFilterRows((rows) =>
                                            rows.length === 1 ? [{ path: '', value: '' }] : rows.filter((_, i) => i !== index),
                                        )
                                    }
                                >
                                    ✕
                                </Button>
                            </div>
                        ))}
                        <div>
                            <Button
                                variant="ghost"
                                onClick={() => setFilterRows((rows) => [...rows, { path: '', value: '' }])}
                            >
                                + Add condition
                            </Button>
                        </div>
                        {filterErrors.length > 0 && (
                            <p className="text-xs text-status-critical">{filterErrors.join('；')}</p>
                        )}
                    </div>
                </form>
            )}
        </Modal>
    )
}
