import { useTheme } from '../context/ThemeContext'

export function ThemeToggle() {
    const { theme, toggleTheme } = useTheme()
    const next = theme === 'dark' ? 'light' : 'dark'

    return (
        <button
            type="button"
            onClick={toggleTheme}
            title={`Switch to ${next} theme`}
            aria-label={`Switch to ${next} theme`}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2 py-1 text-xs font-medium text-ink-secondary hover:bg-plane hover:text-ink"
        >
            <span aria-hidden>{theme === 'dark' ? '☾' : '☀'}</span>
            {theme === 'dark' ? 'Dark' : 'Light'}
        </button>
    )
}
