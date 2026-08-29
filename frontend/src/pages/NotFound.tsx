import { Link } from 'react-router-dom'

export function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-2 bg-plane text-center">
      <p className="text-lg font-semibold text-ink">Page not found</p>
      <Link to="/" className="text-sm font-medium text-accent">
        Back to tasks
      </Link>
    </div>
  )
}
