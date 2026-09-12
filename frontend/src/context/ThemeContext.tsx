import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'coworkify.theme'

interface ThemeValue {
    theme: Theme
    toggleTheme: () => void
}

const ThemeContext = createContext<ThemeValue>({ theme: 'light', toggleTheme: () => { } })

/**
 * 刻意只有 light / dark 兩個狀態，沒有「跟隨系統」——跟隨系統就代表
 * prefers-color-scheme 一變動畫面就換色，那正是要消掉的行為。
 * 只有第一次造訪、還沒有存過偏好時，才拿系統設定當起始值。
 */
function initialTheme(): Theme {
    try {
        const stored = localStorage.getItem(STORAGE_KEY)
        if (stored === 'dark' || stored === 'light') return stored
    } catch {
        // 無痕模式 / 封鎖 site data 時讀不到，往下拿系統預設
    }
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
    const [theme, setTheme] = useState<Theme>(initialTheme)

    useEffect(() => {
        document.documentElement.dataset.theme = theme
        try {
            localStorage.setItem(STORAGE_KEY, theme)
        } catch {
            // 寫不進去也不影響這次 session
        }
    }, [theme])

    const toggleTheme = useCallback(() => setTheme((t) => (t === 'dark' ? 'light' : 'dark')), [])

    return <ThemeContext.Provider value={{ theme, toggleTheme }}>{children}</ThemeContext.Provider>
}

export function useTheme() {
    return useContext(ThemeContext)
}
