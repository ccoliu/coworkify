import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import {
    ApiError,
    createConnection,
    deleteConnection,
    listConnections,
    updateConnection,
} from '../lib/apiClient'
import type { Connection } from '../lib/types'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { EmptyState } from '../components/EmptyState'
import { Input, Label } from '../components/Field'
import { Modal } from '../components/Modal'
import { Spinner } from '../components/Spinner'
import { useToast } from '../context/ToastContext'
import { formatDateTime } from '../lib/format'

export function Connections() {
    const queryClient = useQueryClient()
    const { push } = useToast()
    // null = 關閉；'new' = 新增；Connection = 換這一筆的值
    const [editing, setEditing] = useState<Connection | 'new' | null>(null)

    const { data: connections, isLoading, isError } = useQuery({
        queryKey: ['connections'],
        queryFn: listConnections,
    })

    const deleteMutation = useMutation({
        mutationFn: deleteConnection,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['connections'] })
            push('Connection deleted', 'success')
        },
        onError: (err) => push(err instanceof ApiError ? err.message : 'Failed to delete connection', 'error'),
    })

    return (
        <div className="flex flex-col gap-5">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-lg font-semibold text-ink">Connections</h1>
                    <p className="text-sm text-ink-muted">
                        Secrets such as API tokens and webhook URLs, stored encrypted. Use one in a step as{' '}
                        <code className="font-mono text-xs">{'{{connections.<name>}}'}</code> — in an{' '}
                        <code className="font-mono text-xs">http_request</code> URL or header, a{' '}
                        <code className="font-mono text-xs">fetch_page</code> URL, or a{' '}
                        <code className="font-mono text-xs">notify</code> webhook URL.
                    </p>
                </div>
                <Button variant="primary" onClick={() => setEditing('new')}>
                    New connection
                </Button>
            </div>

            <Card>
                {isLoading ? (
                    <div className="flex items-center justify-center py-16">
                        <Spinner />
                    </div>
                ) : isError ? (
                    <div className="px-6 py-16 text-center text-sm text-status-critical">Failed to load connections.</div>
                ) : !connections?.length ? (
                    <EmptyState
                        title="No connections yet"
                        description="Add a token or webhook URL once, then reference it from any workflow step."
                    />
                ) : (
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="border-b border-border text-left text-ink-muted">
                                <th className="px-4 py-2.5 font-medium">Name</th>
                                <th className="px-4 py-2.5 font-medium">Use as</th>
                                <th className="px-4 py-2.5 font-medium">Description</th>
                                <th className="px-4 py-2.5 font-medium">Updated</th>
                                <th className="px-4 py-2.5" />
                            </tr>
                        </thead>
                        <tbody>
                            {connections.map((c) => (
                                <tr key={c.id} className="border-b border-border last:border-0">
                                    <td className="px-4 py-3 font-medium text-ink">{c.name}</td>
                                    <td className="px-4 py-3 font-mono text-xs text-ink-secondary">{`{{connections.${c.name}}}`}</td>
                                    <td className="px-4 py-3 text-ink-muted">{c.description || '—'}</td>
                                    <td className="px-4 py-3 text-ink-muted">{formatDateTime(c.updated_at)}</td>
                                    <td className="px-4 py-3 text-right">
                                        <div className="flex justify-end gap-2">
                                            <Button variant="ghost" onClick={() => setEditing(c)}>
                                                Replace value
                                            </Button>
                                            <Button
                                                variant="danger"
                                                disabled={deleteMutation.isPending}
                                                onClick={() => {
                                                    if (window.confirm(`Delete "${c.name}"? Steps that use it will fail until it's recreated.`)) {
                                                        deleteMutation.mutate(c.id)
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
                )}
            </Card>

            {editing && (
                <ConnectionModal connection={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />
            )}
        </div>
    )
}

function ConnectionModal({ connection, onClose }: { connection: Connection | null; onClose: () => void }) {
    const queryClient = useQueryClient()
    const { push } = useToast()
    const [name, setName] = useState('')
    const [value, setValue] = useState('')
    const [description, setDescription] = useState(connection?.description ?? '')

    const mutation = useMutation({
        mutationFn: () =>
            connection
                ? updateConnection(connection.id, { value, description })
                : createConnection({ name, value, description: description || null }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['connections'] })
            push(connection ? 'Connection updated' : 'Connection created', 'success')
            onClose()
        },
        onError: (err) => push(err instanceof ApiError ? err.message : 'Failed to save connection', 'error'),
    })

    function onSubmit(e: FormEvent) {
        e.preventDefault()
        mutation.mutate()
    }

    const nameOk = connection !== null || /^[a-zA-Z0-9_]+$/.test(name)
    const canSubmit = nameOk && value.length > 0

    return (
        <Modal
            title={connection ? `Replace value of ${connection.name}` : 'New connection'}
            onClose={onClose}
            footer={
                <>
                    <Button variant="ghost" onClick={onClose}>
                        Cancel
                    </Button>
                    <Button variant="primary" type="submit" form="connection-form" disabled={mutation.isPending || !canSubmit}>
                        {mutation.isPending ? 'Saving…' : 'Save'}
                    </Button>
                </>
            }
        >
            <form id="connection-form" onSubmit={onSubmit} className="flex flex-col gap-4">
                {!connection && (
                    <div>
                        <Label htmlFor="connection-name">Name</Label>
                        <Input
                            id="connection-name"
                            value={name}
                            placeholder="github"
                            onChange={(e) => setName(e.target.value)}
                            autoFocus
                        />
                        <p className="mt-1 text-xs text-ink-muted">
                            Letters, digits and underscores. Steps refer to it as{' '}
                            <code className="font-mono">{`{{connections.${name || '<name>'}}}`}</code>; it can't be renamed later.
                        </p>
                    </div>
                )}
                <div>
                    <Label htmlFor="connection-value">{connection ? 'New value' : 'Value'}</Label>
                    {/* type=password：不顯示在畫面上，也不會被瀏覽器的自動完成記住成一般欄位 */}
                    <Input
                        id="connection-value"
                        type="password"
                        autoComplete="new-password"
                        value={value}
                        onChange={(e) => setValue(e.target.value)}
                        autoFocus={connection !== null}
                    />
                    <p className="mt-1 text-xs text-ink-muted">Stored encrypted. It's never shown again — to change it, replace it.</p>
                </div>
                <div>
                    <Label htmlFor="connection-description">Description (optional)</Label>
                    <Input
                        id="connection-description"
                        value={description}
                        placeholder="Read-only token for apache/airflow"
                        onChange={(e) => setDescription(e.target.value)}
                    />
                </div>
            </form>
        </Modal>
    )
}
