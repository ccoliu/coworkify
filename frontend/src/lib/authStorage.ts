const STORAGE_KEY = 'coworkify.token'

export function getAuthToken(): string | null {
    return localStorage.getItem(STORAGE_KEY)
}

export function setAuthToken(token: string) {
    localStorage.setItem(STORAGE_KEY, token)
}

export function clearAuthToken() {
    localStorage.removeItem(STORAGE_KEY)
}
