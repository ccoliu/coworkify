import { Link } from 'react-router-dom'
import { formatRelativeTime } from '../../lib/format'
import type { WorkflowDefinition } from '../../lib/types'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { StatusBadge } from '../../components/StatusBadge'

export function DefinitionTable({
    definitions,
    onDelete,
}: {
    definitions: WorkflowDefinition[],
    onDelete: (id: string) => void,
}) {
    if (definitions.length == 0) {
        return (
            <EmptyState
                title="No workflows yet"
                description="Build a workflow once, then run it as many times as you like with different input."
            />
        )
    }

    return (
        <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
                <thead>
                    <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-ink-muted">
                        <th className="px-4 py-2.5 font-medium">Name</th>
                        <th className="px-4 py-2.5 font-medium">Steps</th>
                        <th className="px-4 py-2.5 font-medium">Runs</th>
                        <th className="px-4 py-2.5 font-medium">Last run</th>
                        <th className="px-4 py-2.5" />
                    </tr>
                </thead>
                <tbody>
                    {definitions.map((d) => (
                        <tr key={d.id} className="border-b border-border last:border-0 hover:bg-surface">
                            <td className="px-4 py-3">
                                <Link to={`/definitions/${d.id}`} className="font-medium text-ink hover:text-accent">
                                    {d.name}
                                </Link>
                                <div className="text-xs text-ink-muted">
                                    v{d.version}
                                    {d.input_schema.length > 0 && ` · ${d.input_schema.length} input fields`}
                                </div>
                            </td>
                            <td className="px-4 py-3 text-ink-secondary">{d.steps.length}</td>
                            <td className="px-4 py-3 text-ink-secondary">{d.run_count}</td>
                            <td className="px-4 py-3">
                                {d.last_run ? (
                                    <Link to={`/workflows/${d.last_run.id}`} className="flex items-center gap-2">
                                        <StatusBadge status={d.last_run.status} />
                                        <span className="text-xs text-ink-muted">
                                            {formatRelativeTime(d.last_run.created_at)}
                                        </span>
                                    </Link>
                                ) : (
                                    <span className="text-xs text-ink-muted">never</span>
                                )}
                            </td>
                            <td className="px-4 py-3">
                                <div className="flex justify-end gap-2">
                                    <Link to={`/definitions/${d.id}`}>
                                        <Button variant="secondary">Run</Button>
                                    </Link>
                                    <Link to={`/definitions/${d.id}/edit`}>
                                        <Button variant="ghost">Edit</Button>
                                    </Link>
                                    <Button
                                        variant="danger"
                                        onClick={() => {
                                            if (confirm(`Delete workflow "${d.name}"? Its schedules are removed too; past runs are kept.`)) onDelete(d.id)
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
    )
}