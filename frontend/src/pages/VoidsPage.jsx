import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api'
import { PESO, flattenErrors, formatTime } from '../utils'

const TABS = [['pending', 'Waiting'], ['approved', 'Approved'], ['rejected', 'Rejected'], ['all', 'All']]
const COLOR = { pending: '#b86e00', approved: '#1b7f3b', rejected: '#c0392b' }

export default function VoidsPage() {
  const [tab, setTab] = useState('pending')
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    try {
      const response = await apiFetch(`/voids/?status=${tab}`)
      if (response.ok) { setData(await response.json()); setError('') }
      else if (response.status !== 401) setError('Could not load the requests.')
    } catch {
      setError('Cannot reach the server. Is Django running?')
    }
  }, [tab])

  useEffect(() => { load() }, [load])

  async function decide(id, action, note, done) {
    try {
      const response = await apiFetch(`/voids/${id}/${action}/`, { method: 'POST', body: JSON.stringify({ note }) })
      if (response.ok) { setNotice(done); await load(); return '' }
      if (response.status === 400) return flattenErrors(await response.json()).join(' ')
      if (response.status === 401) return 'Your session ended. Please log in again.'
      return 'Something went wrong. Please try again.'
    } catch {
      return 'Cannot reach the server. Is Django running?'
    }
  }

  return (
    <div style={{ maxWidth: 900 }}>
      <h1>Voids</h1>
      <p style={{ color: '#555' }}>
        A cashier asks to void a sale. Nothing changes until you approve. Approving puts the stock back, and
        either books the cash refund as a pay-out in the shift open now (when the sale's shift is already closed)
        or lowers the customer's utang. The sale stays in the records, marked VOID.
      </p>
      <div style={{ display: 'flex', gap: 8, margin: '10px 0' }}>
        {TABS.map(([id, label]) => (
          <button key={id} onClick={() => { setTab(id); setNotice('') }} disabled={tab === id} style={{ padding: '8px 14px' }}>
            {label}{id === 'pending' && data ? ` (${data.pending_count})` : ''}
          </button>
        ))}
      </div>
      {notice && <p style={{ background: '#f3fbf5', border: '1px solid #1b7f3b', padding: 10, borderRadius: 6 }}>{notice}</p>}
      {error && <p style={{ color: 'crimson', fontSize: 18 }}>{error}</p>}
      {data && data.requests.length === 0 && <p style={{ color: '#777' }}>Nothing here.</p>}
      {data?.requests.map((v) => <Row key={v.id} v={v} onDecide={decide} />)}
    </div>
  )
}

function Row({ v, onDecide }) {
  const [mode, setMode] = useState(null)  
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)

  const effect = v.payment_type === 'utang'
    ? `${v.customer}'s utang goes down by ${PESO}${v.total}. No cash.`
    : `Give ${PESO}${v.total} back to the customer. If the sale's shift is closed, it is booked as a pay-out in the shift open now.`

  async function submit(event) {
    event.preventDefault()
    if (busyRef.current) return
    if (mode === 'reject' && !note.trim()) return setError('Enter the reason for rejecting. It is required.')
    if (mode === 'approve' && !window.confirm(`Void ${v.receipt_no} (${PESO}${v.total})?\n\nThe stock is put back. ${effect}\n\nThis cannot be undone.`)) return
    busyRef.current = true
    setBusy(true)
    const message = await onDecide(v.id, mode, note.trim(), mode === 'approve' ? `${v.receipt_no} voided.` : `${v.receipt_no} request rejected.`)
    busyRef.current = false
    setBusy(false)
    if (message) setError(message)
  }

  return (
    <div style={{ border: '1px solid #ccc', borderRadius: 8, padding: 12, marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 6 }}>
        <b>{v.receipt_no} &middot; {PESO}{v.total} &middot; {v.payment_type === 'utang' ? `Utang (${v.customer})` : 'Cash'}</b>
        <b style={{ color: COLOR[v.status] }}>{v.status.toUpperCase()}</b>
      </div>
      <div>Sold by {v.sold_by}, {formatTime(v.sold_at)} (shift #{v.sale_shift ?? '-'})</div>
      <div>Requested by <b>{v.requested_by}</b>, {formatTime(v.requested_at)}</div>
      <div style={{ margin: '4px 0' }}>Reason: <b>{v.reason}</b></div>
      {v.status !== 'pending' && (
        <div style={{ color: '#555' }}>
          {v.status === 'approved' ? 'Approved' : 'Rejected'} by {v.decided_by}, {formatTime(v.decided_at)}
          {v.decision_note && `: ${v.decision_note}`}
          {parseFloat(v.refund_amount) > 0 && ` | refund ${PESO}${v.refund_amount} booked in shift #${v.refund_shift}`}
        </div>
      )}
      {v.status === 'pending' && !mode && (
        <div style={{ marginTop: 6 }}>
          <button onClick={() => setMode('approve')} style={{ padding: '6px 12px' }}>Approve</button>{' '}
          <button onClick={() => setMode('reject')} style={{ padding: '6px 12px' }}>Reject</button>
        </div>
      )}
      {v.status === 'pending' && mode && (
        <form onSubmit={submit} style={{ marginTop: 6 }}>
          {mode === 'approve' && <p style={{ color: '#555', margin: '4px 0' }}>{effect}</p>}
          <input style={{ padding: 8, width: '100%', maxWidth: 420, boxSizing: 'border-box' }} maxLength={200} value={note}
                 onChange={(e) => setNote(e.target.value)} autoFocus
                 placeholder={mode === 'reject' ? 'Reason for rejecting (required)' : 'Note (optional)'} />
          {error && <div style={{ color: 'crimson' }}>{error}</div>}
          <div style={{ marginTop: 6 }}>
            <button type="submit" disabled={busy} style={{ padding: '6px 12px' }}>{busy ? 'Saving...' : mode === 'approve' ? 'Approve void' : 'Reject'}</button>{' '}
            <button type="button" onClick={() => { setMode(null); setError('') }} disabled={busy} style={{ padding: '6px 12px' }}>Cancel</button>
          </div>
        </form>
      )}
    </div>
  )
}