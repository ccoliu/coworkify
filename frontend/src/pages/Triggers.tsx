import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
    ApiError,
    deleteTrigger,
    hookUrl,
    listDefinitions,
    listTriggers,
    rotateTriggerSecret,
    updateTrigger,
} from '../lib/apiClient'
import type { WorkflowTrigger, WorkflowTriggerWithSecret } from '../lib/types'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { EmptyState } from '../components/EmptyState'
import { Spinner } from '../components/Spinner'
import { useToast } from '../context/ToastContext'
import { formatDateTime, shortId } from '../lib/format'
import { TriggerFormModal } from '../features/triggers/TriggerFormModal'
import { TriggerSecretModal } from '../features/triggers/TriggerSecretModal'

function filterSummary(filter: Record<string, unknown>): string {
    return Object.entries(filter)
        .map(([path, value]) =>
            Array.isArray(value) ? `${path} ∈ ${JSON.stringify(value)}` : `${path} = ${JSON.stringify(value)}`,
        )
        .join(', ')
}

const ON_STATUS_TEXT = { success: 'succeeds', failed: 'fails', any: 'finishes' } as const

export function Triggers() {
    const queryClient = useQueryClient()
    const { push } = useToast()
    // null = 關閉；'new' = 新增；WorkflowTrigger = 編輯這一筆
    const [editing, setEditing] = useState<WorkflowTrigger | 'new' | null>(null)
    // 剛建立或剛換 secret 的那一筆，顯示一次 secret
    const [revealed, setRevealed] = useState<WorkflowTriggerWithSecret | null>(null)

    const { data: triggers, isLoading, isError } = useQuery({
        queryKey: ['triggers'],
        queryFn: listTriggers,
    })
    // 觸發器只帶 definition_id，名稱從定義列表對回來
    const { data: definitions } = useQuery({
        queryKey: ['definitions'],
        queryFn: () => listDefinitions(100),
    })
    const definitionName = (id: string) => definitions?.find((d) => d.id === id)?.name ?? shortId(id)

    const invalidate = () => queryClient.invalidateQueries({ queryKey: ['triggers'] })
    const onError = (fallback: string) => (err: unknown) =>
        push(err instanceof ApiError ? err.message : fallback, 'error')

    const toggleMutation = useMutation({
        mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => updateTrigger(id, { enabled }),
        onSuccess: invalidate,
        onError: onError('Failed to update trigger'),
    })

    const rotateMutation = useMutation({
        mutationFn: rotateTriggerSecret,
        onSuccess: (rotated) => {
            invalidate()
            setRevealed(rotated)
        },
        onError: onError('Failed to rotate secret'),
    })

    const deleteMutation = useMutation({
        mutationFn: deleteTrigger,
        onSuccess: () => {
            invalidate()
            push('Trigger deleted', 'success')
        },
        onError: onError('Failed to delete trigger'),
    })

    async function copyUrl(trigger: WorkflowTrigger) {
        try {
            if (!trigger.hook_path) return
            await navigator.clipboard.writeText(hookUrl(trigger.hook_path))
            push('Webhook URL copied', 'success')
        } catch {
            push('Copy failed', 'error')
        }
    }

    return (
        <div className="flex flex-col gap-5">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-lg font-semibold text-ink">Triggers</h1>
                    <p className="text-sm text-ink-muted">
                        Start a workflow when an outside system calls a webhook — GitHub, or your own script — or when a run of
                        another workflow finishes.
                    </p>
                </div>
                <Button variant="primary" onClick={() => setEditing('new')}>
                    New trigger
                </Button>
            </div>

            <Card>
                {isLoading ? (
                    <div className="flex items-center justify-center py-16">
                        <Spinner />
                    </div>
                ) : isError ? (
                    <div className="px-6 py-16 text-center text-sm text-status-critical">Failed to load triggers.</div>
                ) : !triggers?.length ? (
                    <EmptyState
                        title="No triggers yet"
                        description="Start a workflow from GitHub events or any HTTP call, or chain it after another workflow."
                    />
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full border-collapse text-sm">
                            <thead>
                                <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-ink-muted">
                                    <th className="px-4 py-2.5 font-medium">Name</th>
                                    <th className="px-4 py-2.5 font-medium">Workflow</th>
                                    <th className="px-4 py-2.5 font-medium">Runs when</th>
                                    <th className="px-4 py-2.5 font-medium">Last triggered</th>
                                    <th className="px-4 py-2.5 font-medium">Enabled</th>
                                    <th className="px-4 py-2.5 font-medium" />
                                </tr>
                            </thead>
                            <tbody>
                                {triggers.map((t) => (
                                    <tr key={t.id} className="border-b border-border last:border-0 hover:bg-surface">
                                        <td className="px-4 py-3">
                                            <div className="font-medium text-ink">{t.name}</div>
                                            {t.hook_path ? (
                                                <button
                                                    onClick={() => copyUrl(t)}
                                                    className="font-mono text-xs text-ink-muted hover:text-accent"
                                                    title="Copy webhook URL"
                                                >
                                                    {t.hook_path}
                                                </button>
                                            ) : (
                                                <div className="text-xs text-ink-muted">after another workflow</div>
                                            )}
                                        </td>
                                        <td className="px-4 py-3">
                                            <Link to={`/definitions/${t.definition_id}`} className="text-ink hover:text-accent">
                                                {definitionName(t.definition_id)}
                                            </Link>
                                        </td>
                                        <td className="max-w-xs px-4 py-3 text-xs text-ink-secondary">
                                            {t.kind === 'workflow' && t.source_definition_id ? (
                                                <div>
                                                    after{' '}
                                                    <Link
                                                        to={`/definitions/${t.source_definition_id}`}
                                                        className="font-medium text-ink hover:text-accent"
                                                    >
                                                        {definitionName(t.source_definition_id)}
                                                    </Link>{' '}
                                                    {ON_STATUS_TEXT[t.on_status ?? 'success']}
                                                </div>
                                            ) : (
                                                !Object.keys(t.filter).length && <div>every request</div>
                                            )}
                                            {Object.keys(t.filter).length > 0 && (
                                                <div className="font-mono">{filterSummary(t.filter)}</div>
                                            )}
                                        </td>
                                        <td className="px-4 py-3 text-ink-muted">
                                            {t.last_error ? (
                                                <div className="text-status-critical" title={t.last_error}>
                                                    Failed · {t.last_error_at ? formatDateTime(t.last_error_at) : ''}
                                                    <div className="max-w-xs truncate text-xs">{t.last_error}</div>
                                                </div>
                                            ) : t.last_triggered_at ? (
                                                formatDateTime(t.last_triggered_at)
                                            ) : (
                                                'Never'
                                            )}
                                        </td>
                                        <td className="px-4 py-3">
                                            <button
                                                onClick={() => toggleMutation.mutate({ id: t.id, enabled: !t.enabled })}
                                                className={`text-xs font-medium ${t.enabled ? 'text-status-good' : 'text-ink-muted'}`}
                                            >
                                                {t.enabled ? 'Enabled' : 'Disabled'}
                                            </button>
                                        </td>
                                        <td className="px-4 py-3 text-right">
                                            <div className="flex justify-end gap-1">
                                                <Button variant="ghost" onClick={() => setEditing(t)}>
                                                    Edit
                                                </Button>
                                                {t.kind === 'webhook' && (
                                                <Button
                                                    variant="ghost"
                                                    disabled={rotateMutation.isPending}
                                                    onClick={() => {
                                                        if (
                                                            window.confirm(
                                                                `Rotate the secret of "${t.name}"? The old one stops working immediately — update GitHub or your script with the new one.`,
                                                            )
                                                        ) {
                                                            rotateMutation.mutate(t.id)
                                                        }
                                                    }}
                                                >
                                                    Rotate secret
                                                </Button>
                                                )}
                                                <Button
                                                    variant="ghost"
                                                    className="text-status-critical hover:text-status-critical"
                                                    disabled={deleteMutation.isPending}
                                                    onClick={() => {
                                                        if (window.confirm(`Delete trigger "${t.name}"? Calls to its URL will get 404.`)) {
                                                            deleteMutation.mutate(t.id)
                                                        }
                                                    }}
                                                >
                                                    Delete
                                                </Button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Card>

            {editing && (
                <TriggerFormModal
                    trigger={editing === 'new' ? null : editing}
                    onClose={() => setEditing(null)}
                    onCreated={(created) => {
                        setEditing(null)
                        if (created.secret) {
                            setRevealed(created)
                        } else {
                            push('Trigger created', 'success')
                        }
                    }}
                />
            )}
            {revealed && <TriggerSecretModal trigger={revealed} onClose={() => setRevealed(null)} />}
        </div>
    )
}
