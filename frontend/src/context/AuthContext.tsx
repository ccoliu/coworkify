import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import {
  ApiError,
  fetchMe,
  login as loginRequest,
  register as registerRequest,
} from '../lib/apiClient'
import { clearAuthToken, getAuthToken, setAuthToken } from '../lib/authStorage'
import type { User } from '../lib/types'

interface AuthContextValue {
  user: User | null
  isReady: boolean
  login: (username: string, password: string) => Promise<void>
  register: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isReady, setIsReady] = useState(false)

  useEffect(() => {
    const token = getAuthToken()
    if (!token) {
      setIsReady(true)
      return
    }
    fetchMe()
      .then(setUser)
      .catch(() => clearAuthToken())
      .finally(() => setIsReady(true))
  }, [])

  async function login(username: string, password: string) {
    try {
      const res = await loginRequest(username, password)
      setAuthToken(res.access_token)
      setUser(res.user)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        throw new Error('Invalid username or password.')
      }
      throw new Error('Could not reach the Coworkify API. Is it running?')
    }
  }

  async function register(username: string, password: string) {
    try {
      const res = await registerRequest(username, password)
      setAuthToken(res.access_token)
      setUser(res.user)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        throw new Error('That username is already taken.')
      }
      throw new Error('Could not reach the Coworkify API. Is it running?')
    }
  }

  function logout() {
    clearAuthToken()
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, isReady, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
