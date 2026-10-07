import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { API_URL, apiFetch, clearAuth, getAuth, saveAuth } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => getAuth()?.user ?? null)
  const [checking, setChecking] = useState(() => !!getAuth())

  const logout = useCallback(() => {
    clearAuth()
    setUser(null)
  }, [])

  useEffect(() => {
    if (!getAuth()) return
    apiFetch('/auth/me/')
      .then(async (r) => {
        if (r.ok) {
          const me = await r.json()
          saveAuth({ ...getAuth(), user: me })  
          setUser(me)
        } else {
          logout()
        }
      })
      .catch(() => {})  
      .finally(() => setChecking(false))
  }, [logout])

  useEffect(() => {
    window.addEventListener('auth-expired', logout)
    return () => window.removeEventListener('auth-expired', logout)
  }, [logout])

  async function login(username, password) {
    try {
      const response = await fetch(`${API_URL}/auth/login/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      if (response.status === 429) {
        return { ok: false, error: 'Too many login attempts. Please wait a minute.' }
      }
      if (!response.ok) {
        return { ok: false, error: 'Wrong username or password.' }
      }
      const data = await response.json()
      saveAuth({ access: data.access, refresh: data.refresh, user: data.user })
      setUser(data.user)
      return { ok: true, user: data.user }
    } catch {
      return { ok: false, error: 'Cannot reach the server. Is Django running?' }
    }
  }

  if (checking) return <p style={{ padding: 24 }}>Loading...</p>

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}