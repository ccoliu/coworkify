import {
  createContext,
  useContext,
  useState,
  type ReactNode,
} from 'react'
import { ApiError, listTasks } from '../lib/apiClient'
import { clearApiKey, getApiKey, setApiKey } from '../lib/apiKey'

interface AuthContextValue {
  apiKey: string | null
  login: (key: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [apiKey, setKey] = useState<string | null>(getApiKey)

  async function login(key: string) {
    const trimmed = key.trim()
    setApiKey(trimmed)
    try {
      await listTasks({ limit: 1, offset: 0 })
    } catch (err) {
      clearApiKey()
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        throw new Error('That API key was rejected by the server.')
      }
      throw new Error('Could not reach the Coworkify API. Is it running?')
    }
    setKey(trimmed)
  }

  function logout() {
    clearApiKey()
    setKey(null)
  }

  return (
    <AuthContext.Provider value={{ apiKey, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
