import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
    ApiError,
    deleteDefinition,
    getDefinition,
    listDefinitionRuns,
    rerunWorkflow,
    runDefinition,
} from '../lib/apiClient'
import { formatDateTime } from '../lib/format'
import type { TaskFieldSpec } from '../lib/types'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { EmptyState } from '../components/EmptyState'
import { Spinner } from '../components/Spinner'
import { TaskPayloadFields } from '../features/tasks/TaskPayloadFields'
import { WorkflowTable } from '../features/workflows/WorkflowTable'
import { useToast } from '../context/ToastContext'

/** run 表單的初始值：有 default 用 default，select 沒 default 就先選第一個，免得畫面顯示第一項但值是 null。 */
function initialInput(schema: TaskFieldSpec[]): Record<string, unknown> {
    return Object.fromEntries(
        schema.map((f) => {
            if (f.default !== null && f.default !== undefined) return [f.key, f.default]
            if (f.kind === 'select') return [f.key, f.options?.[0]?.value ?? null]
            if (f.kind === 'multiselect') return [f.key, []]
            if (f.kind === 'boolean') return [f.key, false]
            return [f.key, null]
        })
    )
}

function missingRequired(schema: TaskFieldSpec[], input: Record<string, unknown>): string[] {
    return schema
        .filter((f) => {
            const v = input[f.key]
            return f.required && (v == null || v === '' || (Array.isArray(v) && v.length === 0))
        })
        .map((f) => f.label)
}

export function DefinitionDetail() {
    const { id } = useParams<{ id: string }>()
    const navigate = useNavigate()
    const queryClient = useQueryClient()
    const { push } = useToast()
    const [input, setInput] = useState<Record<string, unknown> | null>(null)

    const { data: definition, isLoading, isError } = useQuery({
        queryKey: ['definition', id],
        queryFn: () => getDefinition(id as string),
        enabled: !!id,
    })

    const { data: runs } = useQuery({
        queryKey: ['definition', id, 'runs'],
        queryFn: () => listDefinitionRuns(id as string),
        enabled: !!id,
        // 有 run 還在跑就慢速輪詢，讓狀態欄自己更新
        refetchInterval: (query) => {
            const running = query.state.data?.some((r) => r.status === 'pending')
            return running ? 3000 : false
        }
    })

    const run = useMutation({
        mutationFn: (values: Record<string, unknown>) => runDefinition(id as string, values),
        onSuccess: (created) => {
            queryClient.invalidateQueries({ queryKey: ['definition', id] })
            queryClient.invalidateQueries({ queryKey: ['definitions'] })
            queryClient.invalidateQueries({ queryKey: ['workflows'] })
            push('Run started', 'success')
            navigate(`/workflows/${created.id}`)
        },
        onError: (err) => {
            push(err instanceof ApiError ? err.message : 'Failed to start run', 'error')
        },
    })

    const rerun = useMutation({
        mutationFn: rerunWorkflow,
        onSuccess: (created) => {
            queryClient.invalidateQueries({ queryKey: ['definition', id] })
            push('Re-run started', 'success')
            navigate(`/workflows/${created.id}`)
        },
        onError: (err) => {
            push(err instanceof ApiError ? err.message : 'Failed to re-run workflow', 'error')
        },
    })

    const remove = useMutation({
        mutationFn: deleteDefinition,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['definitions'] })
            push('Workflow deleted', 'success')
            navigate('/workflows')
        },
        onError: (err) => {
            push(err instanceof ApiError ? err.message : 'Failed to delete workflow', 'error')
        },
    })

    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-16">
                <Spinner />
            </div>
        )
    }

    if (isError || !definition) {
        return (
            <EmptyState
                title="Workflow not found"
                action={<Link to="/workflows" className="text-sm font-medium text-accent">Back to workflows</Link>}
            />
        )
    }

    const schema = definition.input_schema
    // 定義載入前沒辦法算初始值，所以用 null 表示「使用者還沒動過」，動過才存進 state
    const values = input ?? initialInput(schema)
    const missing = missingRequired(schema, values)

    function onRun(e: FormEvent) {
        e.preventDefault()
        run.mutate(schema.length > 0 ? values : {})
    }

    return (
        <div className="flex flex-col gap-5">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <Link to="/workflows" className="text-sm text-ink-muted hover:text-ink">
                        ← Workflows
                    </Link>
                    <div className="mt-1 flex items-center gap-3">
                        <h1 className="text-lg font-semibold text-ink">{definition.name}</h1>
                        <span className="rounded-full border border-border px-2 py-0.5 text-xs text-ink-muted">
                            v{definition.version}
                        </span>
                    </div>
                    {definition.description && (
                        <p className="mt-1 text-sm text-ink-secondary">{definition.description}</p>
                    )}
                    <p className="mt-1 text-xs text-ink-muted">Updated {formatDateTime(definition.updated_at)}</p>
                </div>
                <div className="flex items-center gap-2">
                    <Link to={`/definitions/${definition.id}/edit`}>
                        <Button variant="secondary">Edit</Button>
                    </Link>
                    <Button
                        variant="danger"
                        onClick={() => {
                            if (confirm(`Delete workflow "${definition.name}"? Its past runs are kept.`)) {
                                remove.mutate(definition.id)
                            }
                        }}
                    >
                        Delete
                    </Button>
                </div>
            </div>

            <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                <Card className="p-5">
                    <form onSubmit={onRun} className="flex flex-col gap-4">
                        <h2 className="text-sm font-semibold text-ink">Run</h2>
                        {schema.length > 0 ? (
                            <TaskPayloadFields
                                idPrefix={`run-${definition.id}`}
                                fields={schema}
                                payload={values}
                                onChange={setInput}
                            />
                        ) : (
                            <p className="text-sm text-ink-muted">
                                這個 workflow 沒有宣告輸入欄位，會用各步驟裡寫死的設定執行。
                            </p>
                        )}
                        {missing.length > 0 && (
                            <p className="text-xs text-status-critical">必填：{missing.join('、')}</p>
                        )}
                        <div>
                            <Button variant="primary" type="submit" disabled={run.isPending || missing.length > 0}>
                                {run.isPending ? 'Starting…' : 'Run workflow'}
                            </Button>
                        </div>
                    </form>
                </Card>

                <Card className="p-5">
                    <h2 className="mb-3 text-sm font-semibold text-ink">Steps ({definition.steps.length})</h2>
                    <ol className="flex flex-col gap-1.5">
                        {definition.steps.map((s) => (
                            <li key={s.key} className="flex items-center justify-between gap-3 text-sm">
                                <span className="truncate text-ink">{s.name}</span>
                                <span className="shrink-0 font-mono text-xs text-ink-muted">
                                    {s.key} · {s.task_type}
                                </span>
                            </li>
                        ))}
                    </ol>
                </Card>
            </div>

            <Card>
                <div className="border-b border-border px-4 py-3">
                    <h2 className="text-sm font-semibold text-ink">Runs ({definition.run_count})</h2>
                </div>
                {runs ? (
                    <WorkflowTable
                        workflows={runs}
                        onRerun={rerun.mutate}
                        isRerunning={rerun.isPending}
                    />
                ) : (
                    <div className="flex items-center justify-center py-10">
                        <Spinner />
                    </div>
                )}
            </Card>
        </div>
    )
}