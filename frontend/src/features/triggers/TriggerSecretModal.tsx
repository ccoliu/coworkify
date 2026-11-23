import { hookUrl } from '../../lib/apiClient'
import type { WorkflowTriggerWithSecret } from '../../lib/types'
import { Button } from '../../components/Button'
import { Modal } from '../../components/Modal'
import { useToast } from '../../context/ToastContext'

function CopyRow({ label, value, secret }: { label: string; value: string; secret?: boolean }) {
    const { push } = useToast()

    async function copy() {
        try {
            await navigator.clipboard.writeText(value)
            push(`${label} copied`, 'success')
        } catch {
            push('Copy failed — select the text and copy it manually', 'error')
        }
    }

    return (
        <div>
            <p className="mb-1.5 text-sm font-medium text-ink-secondary">{label}</p>
            <div className="flex items-center gap-2">
                <code
                    className={`flex-1 select-all break-all rounded-lg border border-border bg-plane px-3 py-2 font-mono text-xs ${
                        secret ? 'text-status-critical' : 'text-ink'
                    }`}
                >
                    {value}
                </code>
                <Button variant="secondary" onClick={copy}>
                    Copy
                </Button>
            </div>
        </div>
    )
}

/**
 * 建立或換 secret 之後顯示一次。關掉就再也拿不到——API 只存加密後的值、不會再回傳。
 */
export function TriggerSecretModal({ trigger, onClose }: { trigger: WorkflowTriggerWithSecret; onClose: () => void }) {
    const url = hookUrl(trigger.hook_path ?? '')
    const secret = trigger.secret ?? ''
    const curl = `curl -X POST '${url}' \\\n  -H 'Authorization: Bearer ${secret}' \\\n  -H 'Content-Type: application/json' \\\n  -d '{"action": "opened"}'`

    return (
        <Modal
            title={`Webhook for ${trigger.name}`}
            onClose={onClose}
            footer={
                <Button variant="primary" onClick={onClose}>
                    I've saved the secret
                </Button>
            }
        >
            <div className="flex flex-col gap-4">
                <p className="rounded-lg border border-status-warning/40 bg-status-warning/10 px-3 py-2 text-sm text-ink">
                    這是唯一一次看得到 secret。關掉之後只能用「Rotate secret」換一組新的。
                </p>

                <CopyRow label="Webhook URL" value={url} />
                <CopyRow label="Secret" value={secret} secret />

                <div className="flex flex-col gap-2 border-t border-border pt-4 text-sm text-ink-secondary">
                    <p className="font-medium text-ink">GitHub</p>
                    <ol className="list-decimal space-y-1 pl-5 text-xs">
                        <li>Repository → Settings → Webhooks → Add webhook</li>
                        <li>
                            Payload URL 填上面的網址；Content type 選 <code className="font-mono">application/json</code>
                        </li>
                        <li>Secret 填上面的 secret——GitHub 會用它簽每個請求，這邊驗證簽章</li>
                        <li>選要送的事件，例如 Issues。建立時 GitHub 送的 ping 會直接回 pong</li>
                    </ol>
                    <p className="text-xs text-ink-muted">
                        GitHub 要能連到這個網址才行。Coworkify 跑在本機時，需要先用 cloudflared 或 ngrok 開一條 tunnel，
                        把上面網址的網域換成 tunnel 給的網址。
                    </p>
                </div>

                <div className="flex flex-col gap-2 border-t border-border pt-4">
                    <p className="text-sm font-medium text-ink">curl / 自己的腳本</p>
                    <pre className="overflow-x-auto rounded-lg border border-border bg-plane px-3 py-2 font-mono text-xs text-ink">
                        {curl}
                    </pre>
                    <p className="text-xs text-ink-muted">
                        同一個事件可能重送時，帶上 <code className="font-mono">Idempotency-Key</code> header，
                        相同的值只會建立一次 run。
                    </p>
                </div>
            </div>
        </Modal>
    )
}
