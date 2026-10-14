import { useRef, useState } from 'react'
import { apiFetch } from '../api'
import { flattenErrors } from '../utils'

export default function VoidRequestForm({ receiptNo }) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)

  async function submit(event) {
    event.preventDefault()
    if (busyRef.current) return
    if (!reason.trim()) return setError('Enter the reason. It is required.')
    busyRef.current = true
    setBusy(true)
    setError('')
    try {
      const response = await apiFetch(`/sales/${encodeURIComponent(receiptNo)}/void-request/`, {
        method: 'POST', body: JSON.stringify({ reason: reason.trim() }),
      })
      if (response.status === 201) setSent(true)
      else if (response.status === 400 || response.status === 404) setError(flattenErrors(await response.json()).join(' '))
      else if (response.status !== 401) setError('Something went wrong. Check "My void requests" before trying again.')
    } catch {
      setError('Cannot reach the server. Is Django running?')
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  if (sent) return <p style={{ color: '#1b7f3b', maxWidth: 300 }}>Request sent. Nothing changes until the owner approves it.</p>
  if (!open) return <button onClick={() => setOpen(true)} style={{ marginTop: 8, padding: '8px 12px' }}>Request void</button>
  return (
    <form onSubmit={submit} style={{ marginTop: 8, maxWidth: 300 }}>
      <input style={{ width: '100%', padding: 8, boxSizing: 'border-box' }} maxLength={200} value={reason}
             onChange={(e) => setReason(e.target.value)} placeholder="Reason (required)" autoFocus />
      {error && <div style={{ color: 'crimson' }}>{error}</div>}
      <button type="submit" disabled={busy} style={{ marginTop: 6, padding: '6px 12px' }}>{busy ? 'Sending...' : 'Send to owner'}</button>{' '}
      <button type="button" onClick={() => setOpen(false)} style={{ marginTop: 6, padding: '6px 12px' }}>Cancel</button>
    </form>
  )
}