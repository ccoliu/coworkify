import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../components/Button'
import { Card } from '../components/Card'
import { Input, Label } from '../components/Field'
import { useAuth } from '../context/AuthContext'

export function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [key, setKey] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!key.trim()) return
    setLoading(true)
    setError(null)
    try {
      await login(key)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-plane px-4">
      <Card className="w-full max-w-sm p-6">
        <div className="mb-6 flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-accent text-sm font-bold text-white">
            C
          </span>
          <span className="text-base font-semibold text-ink">Coworkify</span>
        </div>
        <p className="mb-5 text-sm text-ink-muted">
          Enter an API key to connect to the task platform.
        </p>
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div>
            <Label htmlFor="api-key">API key</Label>
            <Input
              id="api-key"
              type="password"
              autoFocus
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="changeme_local_dev_key"
            />
          </div>
          {error && <p className="text-sm text-status-critical">{error}</p>}
          <Button type="submit" variant="primary" disabled={loading || !key.trim()}>
            {loading ? 'Connecting…' : 'Connect'}
          </Button>
        </form>
      </Card>
    </div>
  )
}
