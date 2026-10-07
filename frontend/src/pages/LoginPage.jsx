import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'

export default function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to="/" replace />

  async function handleSubmit(event) {
    event.preventDefault()  
    setBusy(true)
    setError('')
    const result = await login(username.trim(), password)
    setBusy(false)
    if (result.ok) {
      navigate(result.user.role === 'OWNER' ? '/owner' : '/cashier', { replace: true })
    } else {
      setError(result.error)
      setPassword('')
    }
  }

  return (
    <div style={{ maxWidth: 360, margin: '80px auto', fontFamily: 'sans-serif', padding: 16 }}>
      <h1>Sari-Sari Store POS</h1>
      <form onSubmit={handleSubmit}>
        <label>
          Username
          <input
            style={inputStyle}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
            autoComplete="username"
            required
          />
        </label>
        <label>
          Password
          <input
            style={inputStyle}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        {error && <p style={{ color: 'crimson' }}>{error}</p>}
        <button type="submit" disabled={busy} style={{ width: '100%', padding: 12, fontSize: 16 }}>
          {busy ? 'Logging in...' : 'Log in'}
        </button>
      </form>
    </div>
  )
}

const inputStyle = {
  display: 'block', width: '100%', padding: 10, margin: '6px 0 14px',
  fontSize: 16, boxSizing: 'border-box',
}