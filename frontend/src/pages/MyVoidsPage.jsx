import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../api'
import { PESO, formatTime } from '../utils'

const COLOR = { pending: '#b86e00', approved: '#1b7f3b', rejected: '#c0392b' }
const WORD = { pending: 'Waiting for the owner', approved: 'Approved', rejected: 'Rejected' }

export default function MyVoidsPage() {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    async function load() {
      try {
        const response = await apiFetch('/voids/mine/')
        if (response.ok) setRows(await response.json())
        else if (response.status !== 401) setError('Could not load your requests.')
      } catch {
        setError('Cannot reach the server. Is Django running?')
      }
    }
    load()
  }, [])

  return (
    <div style={{ maxWidth: 560, margin: '0 auto', padding: 16, fontFamily: 'sans-serif' }}>
      <p><Link to="/">&larr; Back</Link></p>
      <h1>My void requests</h1>
      {error && <p style={{ color: 'crimson' }}>{error}</p>}
      {rows && rows.length === 0 && <p style={{ color: '#777' }}>No requests yet. Open a sale in Receipts and tap "Request void".</p>}
      {rows?.map((v) => (
        <div key={v.id} style={{ border: '1px solid #ccc', borderRadius: 8, padding: 12, marginBottom: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <b>{v.receipt_no} &middot; {PESO}{v.total}</b>
            <b style={{ color: COLOR[v.status] }}>{WORD[v.status]}</b>
          </div>
          <div>Reason: {v.reason}</div>
          {v.decision_note && <div style={{ color: '#555' }}>Owner: {v.decision_note}</div>}
          <small style={{ color: '#777' }}>Asked {formatTime(v.requested_at)}</small>
        </div>
      ))}
    </div>
  )
}