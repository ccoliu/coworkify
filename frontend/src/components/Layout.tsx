import clsx from 'clsx'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { ConnectionIndicator } from './ConnectionIndicator'

const NAV_ITEMS = [
  { to: '/', label: 'Tasks', end: true },
  { to: '/ops', label: 'Ops', end: false },
  { to: '/workflows', label: 'Workflows', end: false },
  { to: '/schedules', label: 'Schedules', end: false },
  { to: '/runners', label: 'Runners', end: false },
]

export function Layout() {
  const { user, logout } = useAuth()

  return (
    <div className="min-h-screen bg-plane">
      <div className="mx-auto flex min-h-screen max-w-6xl">
        <aside className="hidden w-56 shrink-0 flex-col border-r border-border px-4 py-6 sm:flex">
          <div className="mb-8 flex items-center gap-2 px-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-accent text-sm font-bold text-white">
              C
            </span>
            <span className="text-sm font-semibold text-ink">Coworkify</span>
          </div>
          <nav className="flex flex-col gap-1">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  clsx(
                    'rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-accent/10 text-accent'
                      : 'text-ink-secondary hover:bg-surface hover:text-ink',
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="mt-auto flex flex-col gap-3 px-2 pt-6 text-xs text-ink-muted">
            <ConnectionIndicator />
            <div className="flex items-center justify-between gap-2 border-t border-border pt-3">
              <span className="truncate font-medium text-ink-secondary">{user?.username}</span>
              <button
                onClick={logout}
                className="shrink-0 font-medium text-ink-secondary hover:text-ink"
              >
                Sign out
              </button>
            </div>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center justify-between border-b border-border px-6 py-4 sm:hidden">
            <span className="text-sm font-semibold text-ink">Coworkify</span>
            <ConnectionIndicator />
          </header>
          <nav className="flex gap-1 border-b border-border px-4 py-2 sm:hidden">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  clsx(
                    'rounded-lg px-3 py-1.5 text-sm font-medium',
                    isActive ? 'bg-accent/10 text-accent' : 'text-ink-secondary',
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <main className="flex-1 px-6 py-6">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  )
}
