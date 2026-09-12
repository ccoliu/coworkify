import { Link } from 'react-router-dom'
import { formatRelativeTime, shortId } from '../../lib/format'
import type { Workflow } from '../../lib/types'
import { EmptyState } from '../../components/EmptyState'
import { StatusBadge } from '../../components/StatusBadge'
import { Button } from '../../components/Button'

export function WorkflowTable({ workflows, onDelete }: { workflows: Workflow[]; onDelete: (id: string) => void }) {
    if (workflows.length === 0) {
        return (
            <EmptyState
                title="No workflows yet"
                description="Create a workflow to chain multiple tasks together with dependencies."
            />
        )
    }

    return (
        <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
                <thead>
                    <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-ink-muted">
                        <th className="px-4 py-2.5 font-medium">Name</th>
                        <th className="px-4 py-2.5 font-medium">Status</th>
                        <th className="px-4 py-2.5 font-medium">Steps</th>
                        <th className="px-4 py-2.5 font-medium">Updated</th>
                        <th className="px-4 py-2.5" />
                    </tr>
                </thead>
                <tbody>
                    {workflows.map((wf) => {
                        const done = wf.steps.filter((s) => s.task_status === 'success').length
                        return (
                            <tr key={wf.id} className="border-b border-border last:border-0 hover:bg-surface">
                                <td className="px-4 py-3">
                                    <Link to={`/workflows/${wf.id}`} className="font-medium text-ink hover:text-accent">
                                        {wf.name}
                                    </Link>
                                    <div className="font-mono text-xs text-ink-muted">{shortId(wf.id)}</div>
                                </td>
                                <td className="px-4 py-3">
                                    <StatusBadge status={wf.status} />
                                </td>
                                <td className="px-4 py-3 text-ink-secondary">
                                    {done}/{wf.steps.length}
                                </td>
                                <td className="px-4 py-3 text-ink-muted">{formatRelativeTime(wf.updated_at)}</td>
                                <td className="px-4 py-3 text-right">
                                    <Button
                                        variant="danger"
                                        onClick={() => {
                                            if (confirm(`Delete workflow "${wf.name}"?`)) onDelete(wf.id)
                                        }}
                                    >
                                        Delete
                                    </Button>
                                </td>
                            </tr>
                        )
                    })}
                </tbody>
            </table>
        </div>
    )
}
