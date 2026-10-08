import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../api'
import { PESO, flattenErrors, formatTime } from '../utils'

const MONEY_OK = /^\d+(\.\d{1,2})?$/  

export default function ShiftSummaryPage() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [formKey, setFormKey] = useState(0)   

  const load = useCallback(async () => {
    try {
      const response = await apiFetch('/shifts/summary/')
      if (response.ok) {
        setData(await response.json())
        setError('')
      } else if (response.status !== 401) {
        setError('Could not load your shift. Please try again.')
      }
    } catch {
      setError('Cannot reach the server. Is Django running?')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function savePayout(payload) {
    try {
      const response = await apiFetch('/shifts/payouts/', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      if (response.status === 201) {
        const result = await response.json()
        setNotice(
          result.warnings.length > 0
            ? `Pay-out recorded. Note: ${result.warnings.join(' ')}`
            : 'Pay-out recorded.'
        )
        await load()
        setFormKey((k) => k + 1)
        return ''
      }
      if (response.status === 400) return flattenErrors(await response.json()).join(' ')
      if (response.status === 401) return 'Your session ended. Please log in again.'
      return 'Something went wrong. Check the list below before trying again.'
    } catch {
      return 'Connection lost. The pay-out may or may not have been saved. Check the list below BEFORE recording it again.'
    }
  }

  return (
    <div style={{ maxWidth: 560, margin: '0 auto', padding: 16, fontFamily: 'sans-serif' }}>
      <p><Link to="/">&larr; Back</Link></p>
      <h1>My Shift Summary</h1>

      {loading && <p>Loading...</p>}
      {error && <p style={{ color: 'crimson', fontSize: 18 }}>{error}</p>}

      {!loading && !error && data && !data.shift && (
        <p style={{ background: '#fdecea', padding: 14, borderRadius: 8 }}>
          You have no open shift. <Link to="/shift/start"><b>Start shift</b></Link>
        </p>
      )}

      {!loading && !error && data?.shift && (
        <>
          <p style={{ color: '#555' }}>
            Shift #{data.shift.id}, started {formatTime(data.shift.start_time)}
          </p>

          <div style={{ border: '1px solid #ccc', borderRadius: 8, padding: 14 }}>
            <Row label="Sales made" value={data.sales_count} />
            <Row label="Sales total" value={`${PESO}${data.sales_total}`} />
            <Row label="Money taken out (pay-outs)" value={`${PESO}${data.payouts_total}`} />
          </div>

          {notice && (
            <p style={{ background: '#f3fbf5', border: '1px solid #1b7f3b', padding: 10, borderRadius: 6 }}>{notice}</p>
          )}

          <h2>Take money out of the drawer</h2>
          <PayoutForm key={formKey} onSave={savePayout} />

          <h2>Pay-outs this shift</h2>
          {data.payouts.length === 0 && <p style={{ color: '#777' }}>None yet.</p>}
          {data.payouts.map((p) => (
            <div key={p.id} style={{ borderBottom: '1px solid #ddd', padding: '8px 0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <b>{PESO}{p.amount}</b>
                <span style={{ color: '#555' }}>{formatTime(p.timestamp)}</span>
              </div>
              <div>{p.reason}</div>
            </div>
          ))}

          <p style={{ marginTop: 24 }}><Link to="/shift/end"><b>End shift</b></Link></p>
        </>
      )}
    </div>
  )
}

function Row({ label, value }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: 18 }}>
      <span>{label}</span>
      <b>{value}</b>
    </div>
  )
}

function PayoutForm({ onSave }) {
  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)   

  async function handleSubmit(event) {
    event.preventDefault()
    if (busyRef.current) return
    if (!MONEY_OK.test(amount) || parseFloat(amount) <= 0) {
      return setError('Enter the amount (more than 0, up to 2 decimals).')
    }
    if (!reason.trim()) return setError('Enter the reason. It is required and cannot be changed later.')

    const ok = window.confirm(
      `Record a pay-out of ${PESO}${Number(amount).toFixed(2)}?\n\nReason: ${reason.trim()}\n\n` +
      'It is saved under your name and cannot be edited or deleted.'
    )
    if (!ok) return

    busyRef.current = true
    setBusy(true)
    setError('')
    const message = await onSave({ amount, reason: reason.trim() })   // '' means saved
    busyRef.current = false
    if (message) {
      setError(message)
      setBusy(false)
    }
    
  }

  return (
    <form onSubmit={handleSubmit} style={{ border: '1px solid #999', borderRadius: 8, padding: 14, background: '#fafafa' }}>
      <label>
        Amount ({PESO})
        <input
          style={field}
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ''))}
          placeholder="0.00"
        />
      </label>
      <label style={{ display: 'block', marginTop: 10 }}>
        Reason (required)
        <input
          style={field}
          maxLength={200}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="For example: bought ice, paid the delivery man"
        />
      </label>
      {error && <p style={{ color: 'crimson', fontSize: 16 }}>{error}</p>}
      <button type="submit" disabled={busy} style={{ width: '100%', padding: 14, fontSize: 18, marginTop: 10 }}>
        {busy ? 'Saving...' : 'Record pay-out'}
      </button>
    </form>
  )
}

const field = { display: 'block', width: '100%', padding: 10, marginTop: 4, fontSize: 18, boxSizing: 'border-box' }