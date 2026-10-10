import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api'
import { PESO, flattenErrors, formatTime, toCents } from '../utils'

const MONEY_OK = /^\d+(\.\d{1,2})?$/   
const FILTERS = [['all', 'All'], ['owing', 'Owing'], ['overdue', 'Overdue']]

export default function OwnerCustomersPage() {
  const [filter, setFilter] = useState('all')
  const [q, setQ] = useState('')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [version, setVersion] = useState(0)
  const latest = useRef(0)   // ignores stale answers

  useEffect(() => {
    const myRequest = ++latest.current
    const timer = setTimeout(async () => {
      const params = new URLSearchParams()
      params.set('filter', filter)
      if (q.trim()) params.set('q', q.trim())
      try {
        const response = await apiFetch(`/owner/customers/?${params.toString()}`)
        if (myRequest !== latest.current) return
        if (response.ok) {
          setData(await response.json())
          setError('')
        } else if (response.status !== 401) {
          setError('Could not load the customers. Please try again.')
        }
      } catch {
        if (myRequest === latest.current) setError('Cannot reach the server. Is Django running?')
      } finally {
        if (myRequest === latest.current) setLoading(false)
      }
    }, 250)
    return () => clearTimeout(timer)
  }, [filter, q, version])

  const summary = data?.summary

  return (
    <div style={{ maxWidth: 1000 }}>
      <h1>Utang</h1>

      {summary && (
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', margin: '8px 0 16px' }}>
          <Stat label="Total unpaid" value={`${PESO}${summary.total_unpaid}`} />
          <Stat label="Customers owing" value={summary.owing_count} />
          <Stat
            label={`Overdue (over ${summary.overdue_days} days)`}
            value={summary.overdue_count}
            color={summary.overdue_count > 0 ? '#c0392b' : '#1b7f3b'}
          />
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
        {FILTERS.map(([value, label]) => (
          <button key={value} onClick={() => setFilter(value)} disabled={filter === value} style={{ padding: '8px 14px' }}>
            {label}
          </button>
        ))}
        <input
          style={{ padding: 8, fontSize: 16, minWidth: 220 }}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search name or contact"
        />
      </div>

      {selected && (
        <CustomerPanel
          key={selected}
          id={selected}
          onClose={() => setSelected(null)}
          onChanged={() => setVersion((v) => v + 1)}
        />
      )}

      {loading && <p>Loading...</p>}
      {error && <p style={{ color: 'crimson', fontSize: 18 }}>{error}</p>}
      {!loading && !error && data?.customers.length === 0 && <p style={{ color: '#777' }}>No customers to show.</p>}

      {data && data.customers.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 720 }}>
            <thead>
              <tr style={{ textAlign: 'left', borderBottom: '2px solid #333' }}>
                <th style={cell}>Customer</th>
                <th style={cell}>Owes</th>
                <th style={cell}>Limit</th>
                <th style={cell}>Oldest unpaid</th>
                <th style={cell}></th>
              </tr>
            </thead>
            <tbody>
              {data.customers.map((c) => (
                <tr key={c.id} style={{ borderBottom: '1px solid #ddd', opacity: c.is_active ? 1 : 0.5 }}>
                  <td style={cell}>
                    <b>{c.name}</b>{!c.is_active && ' (inactive)'}<br />
                    <small style={{ color: '#555' }}>{c.contact}</small>
                  </td>
                  <td style={{ ...cell, fontWeight: 'bold' }}>{PESO}{c.balance}</td>
                  <td style={cell}>
                    {PESO}{c.credit_limit}<br />
                    <small style={{ color: '#777' }}>{c.personal_limit !== null ? 'personal' : 'store default'}</small>
                  </td>
                  <td style={cell}>
                    {c.days_unpaid === null ? '-' : (
                      <span style={{ color: c.overdue ? '#c0392b' : undefined, fontWeight: c.overdue ? 'bold' : undefined }}>
                        {c.days_unpaid} day(s) {c.overdue && ' OVERDUE'}
                      </span>
                    )}
                  </td>
                  <td style={cell}>
                    <button onClick={() => setSelected(c.id)} style={{ padding: '6px 12px' }}>Open</button>
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

function Stat({ label, value, color }) {
  return (
    <div style={{ border: '1px solid #ccc', borderRadius: 8, padding: '10px 16px', minWidth: 160 }}>
      <div style={{ color: '#555' }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 'bold', color }}>{value}</div>
    </div>
  )
}

function CustomerPanel({ id, onClose, onChanged }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    try {
      const response = await apiFetch(`/owner/customers/${id}/`)
      if (response.ok) {
        setData(await response.json())
        setError('')
      } else if (response.status !== 401) {
        setError('Could not load this customer.')
      }
    } catch {
      setError('Cannot reach the server. Is Django running?')
    }
  }, [id])

  useEffect(() => { load() }, [load])

  
  async function send(path, method, body, doneText) {
    try {
      const response = await apiFetch(path, { method, body: JSON.stringify(body) })
      if (response.ok) {
        setNotice(doneText)
        await load()
        onChanged()
        return ''
      }
      if (response.status === 400) return flattenErrors(await response.json()).join(' ')
      if (response.status === 401) return 'Your session ended. Please log in again.'
      if (response.status === 404) return 'That customer was not found.'
      return 'Something went wrong. Please try again.'
    } catch {
      return 'Cannot reach the server. Is Django running?'
    }
  }

  if (error) return <p style={{ color: 'crimson', fontSize: 18 }}>{error}</p>
  if (!data) return <p>Loading...</p>
  const { customer: c, history } = data
  const owes = toCents(c.balance) > 0

  return (
    <div style={{ border: '2px solid #333', borderRadius: 8, padding: 16, margin: '0 0 20px', background: '#fafafa' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
        <div>
          <h2 style={{ margin: 0 }}>{c.name}</h2>
          <div style={{ color: '#555' }}>{c.contact}</div>
        </div>
        <button onClick={onClose} style={{ padding: '6px 12px', alignSelf: 'flex-start' }}>Close</button>
      </div>

      <div style={{ fontSize: 30, fontWeight: 'bold', margin: '8px 0' }}>Owes {PESO}{c.balance}</div>
      {c.days_unpaid !== null && (
        <div style={{ color: c.overdue ? '#c0392b' : '#555', fontWeight: c.overdue ? 'bold' : 'normal' }}>
          Oldest unpaid charge: {c.days_unpaid} day(s) old
          {c.overdue && ` (over the ${data.overdue_days}-day limit: OVERDUE)`}
        </div>
      )}
      {notice && <p style={{ background: '#f3fbf5', border: '1px solid #1b7f3b', padding: 8, borderRadius: 6 }}>{notice}</p>}

      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 12 }}>
        <LimitForm customer={c} onSave={(value) => send(`/owner/customers/${id}/`, 'PATCH', { credit_limit: value }, 'Credit limit saved.')} />
        {owes && (
          <WriteOffForm
            customer={c}
            onSave={(amount, reason) => send(`/owner/customers/${id}/write-off/`, 'POST', { amount, reason }, 'Write-off recorded.')}
          />
        )}
      </div>

      <ActiveToggle customer={c} onSave={(active) => send(`/owner/customers/${id}/`, 'PATCH', { is_active: active }, active ? 'Customer is active again.' : 'Customer deactivated.')} />

      <h3>History</h3>
      {history.length === 0 && <p style={{ color: '#777' }}>Nothing yet.</p>}
      {history.map((h) => (
        <div key={`${h.kind}-${h.receipt_no}`} style={{ borderBottom: '1px solid #ddd', padding: '6px 0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <b style={{ color: h.kind === 'charge' ? '#000' : h.kind === 'payment' ? '#1b7f3b' : '#b86e00' }}>
              {h.kind === 'charge' ? 'Utang' : h.kind === 'payment' ? 'Paid' : 'Written off'} {PESO}{h.amount}
              {h.status === 'voided' && <span style={{ color: '#c0392b' }}> VOIDED</span>}
            </b>
            <span style={{ color: '#555' }}>{formatTime(h.timestamp)}</span>
          </div>
          <small style={{ color: '#555' }}>
            {h.kind === 'writeoff' ? '' : `${h.receipt_no} · `}balance after {PESO}{h.balance_after} · {h.by}
            {h.reason && ` · reason: ${h.reason}`}
          </small>
        </div>
      ))}
    </div>
  )
}

function LimitForm({ customer, onSave }) {
  const [value, setValue] = useState(customer.personal_limit ?? '')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)

  async function handleSubmit(event) {
    event.preventDefault()
    if (busyRef.current) return
    if (value !== '' && !MONEY_OK.test(value)) return setError('Enter an amount (up to 2 decimals), or leave empty for the store default.')
    busyRef.current = true
    setBusy(true)
    setError('')
    const message = await onSave(value === '' ? null : value)   // '' means saved
    busyRef.current = false
    setBusy(false)
    if (message) setError(message)
  }

  return (
    <form onSubmit={handleSubmit} style={box}>
      <b>Personal credit limit</b>
      <input
        style={field}
        inputMode="decimal"
        value={value}
        onChange={(e) => setValue(e.target.value.replace(/[^\d.]/g, ''))}
        placeholder={`Empty = store default (${PESO}${customer.credit_limit})`}
      />
      <small style={{ color: '#777' }}>Applies to the very next sale.</small>
      {error && <p style={{ color: 'crimson' }}>{error}</p>}
      <button type="submit" disabled={busy} style={{ display: 'block', padding: '8px 14px', marginTop: 8 }}>
        {busy ? 'Saving...' : 'Save limit'}
      </button>
    </form>
  )
}

function WriteOffForm({ customer, onSave }) {
  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)

  async function handleSubmit(event) {
    event.preventDefault()
    if (busyRef.current) return
    if (!MONEY_OK.test(amount) || parseFloat(amount) <= 0) return setError('Enter the amount (more than 0, up to 2 decimals).')
    if (toCents(amount) > toCents(customer.balance)) return setError(`That is more than the balance (${PESO}${customer.balance}).`)
    if (!reason.trim()) return setError('Enter the reason. It is required and permanent.')
    const ok = window.confirm(
      `Write off ${PESO}${Number(amount).toFixed(2)} of ${customer.name}'s debt?\n\nReason: ${reason.trim()}\n\n` +
      'The debt is cancelled, no cash is involved, and this cannot be undone.'
    )
    if (!ok) return
    busyRef.current = true
    setBusy(true)
    setError('')
    const message = await onSave(amount, reason.trim())   // '' means saved
    busyRef.current = false
    setBusy(false)
    if (message) {
      setError(message)
    } else {
      setAmount('')
      setReason('')
    }
  }

  return (
    <form onSubmit={handleSubmit} style={box}>
      <b>Write off bad debt</b>
      <input
        style={field}
        inputMode="decimal"
        value={amount}
        onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ''))}
        placeholder="Amount"
      />
      <button type="button" onClick={() => setAmount(customer.balance)} style={{ padding: '2px 8px', marginBottom: 6 }}>
        Whole balance ({PESO}{customer.balance})
      </button>
      <input
        style={field}
        maxLength={200}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Reason (required)"
      />
      {error && <p style={{ color: 'crimson' }}>{error}</p>}
      <button type="submit" disabled={busy} style={{ display: 'block', padding: '8px 14px', marginTop: 8 }}>
        {busy ? 'Saving...' : 'Write off'}
      </button>
    </form>
  )
}

function ActiveToggle({ customer, onSave }) {
  const [error, setError] = useState('')

  async function toggle() {
    const next = !customer.is_active
    if (!next && !window.confirm(`Deactivate "${customer.name}"? Cashiers will no longer find them. You can reactivate any time.`)) return
    setError('')
    const message = await onSave(next)
    if (message) setError(message)
  }

  return (
    <div style={{ marginTop: 12 }}>
      <button onClick={toggle} style={{ padding: '6px 12px' }}>
        {customer.is_active ? 'Deactivate customer' : 'Reactivate customer'}
      </button>
      {error && <span style={{ color: 'crimson', marginLeft: 10 }}>{error}</span>}
    </div>
  )
}

const cell = { padding: '8px 10px', verticalAlign: 'top' }
const box = { border: '1px solid #999', borderRadius: 8, padding: 12, background: '#fff', minWidth: 260, flex: '1 1 260px' }
const field = { display: 'block', width: '100%', padding: 8, margin: '8px 0', fontSize: 16, boxSizing: 'border-box' }