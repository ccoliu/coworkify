import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { ApiError, createRunner } from '../../lib/apiClient'
import type { RunnerCreated } from '../../lib/types'
import { Button } from '../../components/Button'
import { Input, Label } from '../../components/Field'
import { Modal } from '../../components/Modal'
import { useToast } from '../../context/ToastContext'

export function CreateRunnerModal({ onClose }: { onClose: () => void }) {
    const queryClient = useQueryClient()
    const { push } = useToast()

    const [name, setName] = useState('')
    const [created, setCreated] = useState<RunnerCreated | null>(null)
    const [copied, setCopied] = useState(false)

    const mutation = useMutation({
        mutationFn: () => createRunner(name),
        onSuccess: (runner) => {
            queryClient.invalidateQueries({ queryKey: ['runners'] })
            setCreated(runner)
        },
        onError: (err) => {
            push(err instanceof ApiError ? err.message : 'Failed to create runner', 'error')
        },
    })

    function onSubmit(e: FormEvent) {
        e.preventDefault()
        mutation.mutate()
    }

    async function copyToken() {
        if (!created) return
        try {
            await navigator.clipboard.writeText(created.token)
            setCopied(true)
        } catch {
            push('Copy failed, please select and copy manually', 'error')
        }
    }

    if (created) {
        return (
            <Modal
                title="Runner created"
                onClose={onClose}
                footer={
                    <Button variant="primary" onClick={onClose}>
                        Done
                    </Button>
                }
            >
                <div className="flex flex-col gap-3">
                    <p className="text-sm text-ink-secondary">
                        Copy this token now — it won't be shown again. Use it to start the local agent:
                    </p>
                    <div className="flex items-center gap-2">
                        <code className="flex-1 overflow-x-auto rounded-lg border border-border bg-plane px-3 py-2 text-xs">
                            {created.token}
                        </code>
                        <Button variant="secondary" onClick={copyToken}>
                            {copied ? 'Copied' : 'Copy'}
                        </Button>
                    </div>
                    <pre className="overflow-x-auto rounded-lg border border-border bg-plane px-3 py-2 text-xs text-ink-secondary">
                        {`python agent.py --api <coworkify-api-url> --token ${created.token} --handlers handlers.py`}
                    </pre>
                </div>
            </Modal>
        )
    }

    return (
        <Modal
            title="New runner"
            onClose={onClose}
            footer={
                <>
                    <Button variant="ghost" onClick={onClose}>
                        Cancel
                    </Button>
                    <Button
                        variant="primary"
                        type="submit"
                        form="create-runner-form"
                        disabled={mutation.isPending || !name.trim()}
                    >
                        {mutation.isPending ? 'Creating…' : 'Create runner'}
                    </Button>
                </>
            }
        >
            <form id="create-runner-form" onSubmit={onSubmit} className="flex flex-col gap-4">
                <div>
                    <Label htmlFor="runner-name">Runner name</Label>
                    <Input
                        id="runner-name"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="my-laptop"
                        required
                    />
                </div>
            </form>
        </Modal>
    )
}
