import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api'
import { flattenErrors } from '../utils'

const PIN_OK = /^\d{4,6}$/

const when = (iso) =>
  iso
    ? new Date(iso).toLocaleString('en-PH', { timeZone: 'Asia/Manila', dateStyle: 'medium', timeStyle: 'short' })
    : 'Never'

export default function UsersPage() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [showDisabled, setShowDisabled] = useState(true)
  // null, { mode: 'add' }, { mode: 'password', user }, or { mode: 'pin', user }
  const [panel, setPanel] = useState(null)

  const load = useCallback(async () => {
    try {
      const response = await apiFetch('/users/')
      if (response.ok) {
        setUsers(await response.json())
        setError('')
      } else if (response.status !== 401) {
        setError('Could not load users. Please try again.')
      }
    } catch {
      setError('Cannot reach the server. Is Django running?')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // One helper for every change. Returns '' on success, or a message to show.
  async function send(path, method, body) {
    try {
      const response = await apiFetch(path, { method, body: JSON.stringify(body) })
      if (response.ok) {
        await load()   // always show what the server really saved
        return ''
      }
      if (response.status === 400) return flattenErrors(await response.json()).join(' ')
      if (response.status === 401) return 'Your session ended. Please log in again.'
      if (response.status === 404) return 'That account was not found.'
      return 'Something went wrong. Please try again.'
    } catch {
      return 'Cannot reach the server. Is Django running?'
    }
  }

  async function createCashier(payload) {
    const message = await send('/users/', 'POST', payload)
    if (!message) {
      setPanel(null)
      setNotice(`Cashier "${payload.username}" created.`)
    }
    return message
  }

  async function changeCredential(kind, user, value) {
    const message =
      kind === 'password'
        ? await send(`/users/${user.id}/reset-password/`, 'POST', { new_password: value })
        : await send(`/users/${user.id}/set-pin/`, 'POST', { pin: value })
    if (!message) {
      setPanel(null)
      setNotice(`${kind === 'password' ? 'Password reset' : 'PIN set'} for ${user.username}.`)
    }
    return message
  }

  async function toggleActive(user) {
    const next = !user.is_active
    if (!next) {
      const ok = window.confirm(
        `Disable "${user.username}"?\n\nThey are logged out immediately and cannot log in. ` +
        'Everything they recorded stays in the history. You can enable the account again any time.'
      )
      if (!ok) return
    }
    setNotice('')
    const message = await send(`/users/${user.id}/`, 'PATCH', { is_active: next })
    if (message) setError(message)
    else setNotice(`"${user.username}" is now ${next ? 'enabled' : 'disabled'}.`)
  }

  const visible = users.filter((u) => showDisabled || u.is_active)

  return (
    <div style={{ maxWidth: 900 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <h1 style={{ margin: 0 }}>Users</h1>
        <button onClick={() => { setPanel({ mode: 'add' }); setNotice('') }} disabled={panel !== null} style={{ padding: '10px 16px', fontSize: 16 }}>
          + Add cashier
        </button>
      </div>
      <p style={{ color: '#555' }}>
        Cashier accounts are never deleted, only disabled, so every sale stays traceable to a person.
        Owner accounts are not shown here.
      </p>

      {notice && <p style={{ background: '#f3fbf5', border: '1px solid #1b7f3b', padding: 10, borderRadius: 6 }}>{notice}</p>}

      {panel?.mode === 'add' && (
        <AddForm onSave={createCashier} onCancel={() => setPanel(null)} />
      )}
      {(panel?.mode === 'password' || panel?.mode === 'pin') && (
        <CredentialForm
          key={`${panel.mode}-${panel.user.id}`}
          kind={panel.mode}
          user={panel.user}
          onSave={(value) => changeCredential(panel.mode, panel.user, value)}
          onCancel={() => setPanel(null)}
        />
      )}

      <label style={{ display: 'block', margin: '16px 0' }}>
        <input type="checkbox" checked={showDisabled} onChange={(e) => setShowDisabled(e.target.checked)} />{' '}
        Show disabled accounts
      </label>

      {loading && <p>Loading...</p>}
      {error && <p style={{ color: 'crimson', fontSize: 18 }}>{error}</p>}
      {!loading && !error && visible.length === 0 && <p style={{ color: '#777' }}>No accounts to show.</p>}

      {visible.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 640 }}>
            <thead>
              <tr style={{ textAlign: 'left', borderBottom: '2px solid #333' }}>
                <th style={cell}>Username</th>
                <th style={cell}>Status</th>
                <th style={cell}>PIN</th>
                <th style={cell}>Last login (Manila)</th>
                <th style={cell}></th>
              </tr>
            </thead>
            <tbody>
              {visible.map((u) => (
                <tr key={u.id} style={{ borderBottom: '1px solid #ddd', opacity: u.is_active ? 1 : 0.55 }}>
                  <td style={cell}><b>{u.username}</b></td>
                  <td style={cell}>
                    <span style={{ color: u.is_active ? '#1b7f3b' : '#c0392b', fontWeight: 'bold' }}>
                      {u.is_active ? 'Active' : 'Disabled'}
                    </span>
                  </td>
                  <td style={cell}>{u.has_pin ? 'Set' : 'Not set'}</td>
                  <td style={cell}>{when(u.last_login)}</td>
                  <td style={{ ...cell, whiteSpace: 'nowrap' }}>
                    <button style={btn} disabled={panel !== null} onClick={() => { setPanel({ mode: 'password', user: u }); setNotice('') }}>
                      Reset password
                    </button>{' '}
                    <button style={btn} disabled={panel !== null} onClick={() => { setPanel({ mode: 'pin', user: u }); setNotice('') }}>
                      {u.has_pin ? 'Change PIN' : 'Set PIN'}
                    </button>{' '}
                    <button style={btn} onClick={() => toggleActive(u)}>
                      {u.is_active ? 'Disable' : 'Enable'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function AddForm({ onSave, onCancel }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)

  async function handleSubmit(event) {
    event.preventDefault()
    if (busyRef.current) return
    if (!username.trim()) return setError('Enter a username.')
    if (!password) return setError('Enter a password.')
    if (password !== confirm) return setError('The two passwords do not match.')
    if (pin && !PIN_OK.test(pin)) return setError('PIN must be 4 to 6 digits (or leave it empty).')

    busyRef.current = true
    setBusy(true)
    setError('')
    const payload = { username: username.trim(), password }
    if (pin) payload.pin = pin
    const message = await onSave(payload)   
    busyRef.current = false
    if (message) {
      setError(message)
      setBusy(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} style={formBox}>
      <h2 style={{ marginTop: 0 }}>Add cashier</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
        <label>
          Username
          <input style={field} value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" autoFocus />
        </label>
        <label>
          Password
          <input style={field} type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
          <small style={{ color: '#777' }}>At least 8 characters, not all digits, not a common password.</small>
        </label>
        <label>
          Type the password again
          <input style={field} type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" />
        </label>
        <label>
          PIN (optional)
          <input style={field} type="password" inputMode="numeric" maxLength={6} value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))} autoComplete="off" />
          <small style={{ color: '#777' }}>4 to 6 digits, for fast cashier switching later.</small>
        </label>
      </div>
      {error && <p style={{ color: 'crimson', fontSize: 16 }}>{error}</p>}
      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <button type="submit" disabled={busy} style={{ padding: '10px 18px', fontSize: 16 }}>
          {busy ? 'Saving...' : 'Create cashier'}
        </button>
        <button type="button" onClick={onCancel} disabled={busy} style={{ padding: '10px 18px', fontSize: 16 }}>Cancel</button>
      </div>
    </form>
  )
}

function CredentialForm({ kind, user, onSave, onCancel }) {
  const isPassword = kind === 'password'
  const [value, setValue] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)

  async function handleSubmit(event) {
    event.preventDefault()
    if (busyRef.current) return
    if (!value) return setError(isPassword ? 'Enter the new password.' : 'Enter the PIN.')
    if (!isPassword && !PIN_OK.test(value)) return setError('PIN must be 4 to 6 digits.')
    if (value !== confirm) return setError(isPassword ? 'The two passwords do not match.' : 'The two PINs do not match.')

    busyRef.current = true
    setBusy(true)
    setError('')
    const message = await onSave(value) 
    busyRef.current = false
    if (message) {
      setError(message)
      setBusy(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} style={formBox}>
      <h2 style={{ marginTop: 0 }}>{isPassword ? 'Reset password' : 'Set PIN'}: {user.username}</h2>
      {isPassword && (
        <p style={{ color: '#555' }}>
          The old password cannot be shown, because it is stored as a hash. You set a new one and tell the cashier.
          A cashier who is already logged in stays logged in until their session expires. To cut access
          immediately, <b>Disable</b> the account first.
        </p>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
        <label>
          {isPassword ? 'New password' : 'New PIN (4 to 6 digits)'}
          <input
            style={field}
            type="password"
            inputMode={isPassword ? 'text' : 'numeric'}
            maxLength={isPassword ? undefined : 6}
            value={value}
            onChange={(e) => setValue(isPassword ? e.target.value : e.target.value.replace(/\D/g, ''))}
            autoComplete="new-password"
            autoFocus
          />
        </label>
        <label>
          Type it again
          <input
            style={field}
            type="password"
            inputMode={isPassword ? 'text' : 'numeric'}
            maxLength={isPassword ? undefined : 6}
            value={confirm}
            onChange={(e) => setConfirm(isPassword ? e.target.value : e.target.value.replace(/\D/g, ''))}
            autoComplete="new-password"
          />
        </label>
      </div>
      {error && <p style={{ color: 'crimson', fontSize: 16 }}>{error}</p>}
      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <button type="submit" disabled={busy} style={{ padding: '10px 18px', fontSize: 16 }}>
          {busy ? 'Saving...' : isPassword ? 'Reset password' : 'Save PIN'}
        </button>
        <button type="button" onClick={onCancel} disabled={busy} style={{ padding: '10px 18px', fontSize: 16 }}>Cancel</button>
      </div>
    </form>
  )
}

const cell = { padding: '8px 10px', verticalAlign: 'top' }
const btn = { padding: '6px 10px' }
const formBox = { border: '1px solid #999', borderRadius: 8, padding: 16, margin: '16px 0', background: '#fafafa' }
const field = { display: 'block', width: '100%', padding: 10, marginTop: 4, fontSize: 16, boxSizing: 'border-box' }