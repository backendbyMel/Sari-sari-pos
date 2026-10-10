import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../AuthContext'

const NOTICE_KEY = 'pos_notice'

export default function LoginPage() {
  const { user, login, loginWithPin } = useAuth()
  const navigate = useNavigate()
  const [mode, setMode] = useState('password')     
  const [username, setUsername] = useState('')
  const [secret, setSecret] = useState('')        
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice] = useState(() => sessionStorage.getItem(NOTICE_KEY) ?? '')

  useEffect(() => { sessionStorage.removeItem(NOTICE_KEY) }, [])

  if (user) return <Navigate to="/" replace />

  const isPin = mode === 'pin'

  function switchMode(next) {
    setMode(next)
    setSecret('')
    setError('')
  }

  async function handleSubmit(event) {
    event.preventDefault()   
    if (busy) return
    if (isPin && !/^\d{4,6}$/.test(secret)) {
      return setError('The PIN is 4 to 6 digits.')
    }
    setBusy(true)
    setError('')
    const result = isPin
      ? await loginWithPin(username.trim(), secret)
      : await login(username.trim(), secret)
    setBusy(false)
    if (result.ok) {
      navigate(result.user.role === 'OWNER' ? '/owner' : '/cashier', { replace: true })
    } else {
      setError(result.error)
      setSecret('')
    }
  }

  return (
    <div style={{ maxWidth: 360, margin: '80px auto', fontFamily: 'sans-serif', padding: 16 }}>
      <h1>Sari-Sari Store POS</h1>
      {notice && (
        <p style={{ background: '#fff3cd', padding: 10, borderRadius: 6 }}>{notice}</p>
      )}

      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <button type="button" onClick={() => switchMode('password')} disabled={!isPin} style={{ flex: 1, padding: 8 }}>
          Password
        </button>
        <button type="button" onClick={() => switchMode('pin')} disabled={isPin} style={{ flex: 1, padding: 8 }}>
          Cashier PIN
        </button>
      </div>

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
          {isPin ? 'PIN (4 to 6 digits)' : 'Password'}
          <input
            style={inputStyle}
            type="password"
            inputMode={isPin ? 'numeric' : 'text'}
            maxLength={isPin ? 6 : undefined}
            value={secret}
            onChange={(e) => setSecret(isPin ? e.target.value.replace(/\D/g, '') : e.target.value)}
            autoComplete={isPin ? 'off' : 'current-password'}
            required
          />
        </label>
        {error && <p style={{ color: 'crimson' }}>{error}</p>}
        <button type="submit" disabled={busy} style={{ width: '100%', padding: 12, fontSize: 16 }}>
          {busy ? 'Logging in...' : 'Log in'}
        </button>
      </form>
      {isPin && (
        <p style={{ color: '#777', fontSize: 14 }}>
          PIN login is for cashiers only. The owner always uses a password.
        </p>
      )}
    </div>
  )
}

const inputStyle = {
  display: 'block', width: '100%', padding: 10, margin: '6px 0 14px',
  fontSize: 16, boxSizing: 'border-box',
}