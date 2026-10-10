import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api'
import { PESO, flattenErrors } from '../utils'

export default function CustomerPicker({ selected, onSelect, onClear }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState([])
  const [message, setMessage] = useState('')
  const [registering, setRegistering] = useState(false)
  const latest = useRef(0)   // ignores stale answers

  useEffect(() => {
    if (selected) return undefined
    const myRequest = ++latest.current
    const timer = setTimeout(async () => {
      try {
        const response = await apiFetch(`/customers/?q=${encodeURIComponent(q.trim())}`)
        if (myRequest !== latest.current) return
        if (response.ok) {
          setResults(await response.json())
          setMessage('')
        } else if (response.status !== 401) {
          setMessage('Could not load customers.')
        }
      } catch {
        if (myRequest === latest.current) setMessage('Cannot reach the server. Is Django running?')
      }
    }, 250)
    return () => clearTimeout(timer)
  }, [q, selected])

  if (selected) {
    return (
      <div style={{ border: '1px solid #1b7f3b', background: '#f3fbf5', borderRadius: 8, padding: 10, margin: '8px 0' }}>
        <b>{selected.name}</b>
        <div style={{ color: '#555' }}>{selected.contact}</div>
        <div>Owes {PESO}{selected.balance} &middot; limit {PESO}{selected.credit_limit}</div>
        <button type="button" onClick={onClear} style={{ marginTop: 6, padding: '4px 10px' }}>Change customer</button>
      </div>
    )
  }

  return (
    <div style={{ margin: '8px 0' }}>
      <input
        style={{ width: '100%', padding: 10, fontSize: 16, boxSizing: 'border-box' }}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search customer by name or contact"
        autoComplete="off"
      />
      {message && <p style={{ color: 'crimson' }}>{message}</p>}
      {results.length === 0 && !message && <p style={{ color: '#777' }}>No customers found.</p>}
      {results.map((c) => (
        <button
          type="button" key={c.id} onClick={() => onSelect(c)}
          style={{ display: 'block', width: '100%', textAlign: 'left', padding: 10, margin: '4px 0' }}
        >
          <b>{c.name}</b> <span style={{ color: '#555' }}>{c.contact}</span>
          <div>Owes {PESO}{c.balance}</div>
        </button>
      ))}

      {!registering ? (
        <button type="button" onClick={() => setRegistering(true)} style={{ marginTop: 8, padding: '8px 12px' }}>
          + Register a new customer
        </button>
      ) : (
        <RegisterForm
          initialName={q}
          onCreated={(c) => { setRegistering(false); onSelect(c) }}
          onCancel={() => setRegistering(false)}
        />
      )}
    </div>
  )
}

function RegisterForm({ initialName, onCreated, onCancel }) {
  const [name, setName] = useState(initialName)
  const [contact, setContact] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)

  async function handleSubmit(event) {
    event.preventDefault()
    if (busyRef.current) return
    if (!name.trim() || !contact.trim()) return setError('Enter the name and a phone number or address.')
    busyRef.current = true
    setBusy(true)
    setError('')
    try {
      const response = await apiFetch('/customers/', {
        method: 'POST',
        body: JSON.stringify({ name: name.trim(), contact: contact.trim() }),
      })
      if (response.status === 201) {
        onCreated(await response.json())
        return
      }
      if (response.status === 400) setError(flattenErrors(await response.json()).join(' '))
      else if (response.status !== 401) setError('Something went wrong. Please try again.')
    } catch {
      setError('Cannot reach the server. Is Django running?')
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ border: '1px solid #999', borderRadius: 8, padding: 12, marginTop: 8, background: '#fafafa' }}>
      <b>New customer</b>
      <input style={field} value={name} onChange={(e) => setName(e.target.value)} placeholder="Full name" />
      <input style={field} value={contact} onChange={(e) => setContact(e.target.value)} placeholder="Phone number or address" />
      {error && <p style={{ color: 'crimson' }}>{error}</p>}
      <div style={{ display: 'flex', gap: 8 }}>
        <button type="submit" disabled={busy} style={{ padding: '8px 14px' }}>{busy ? 'Saving...' : 'Register'}</button>
        <button type="button" onClick={onCancel} disabled={busy} style={{ padding: '8px 14px' }}>Cancel</button>
      </div>
    </form>
  )
}

const field = { display: 'block', width: '100%', padding: 8, margin: '8px 0', fontSize: 16, boxSizing: 'border-box' }