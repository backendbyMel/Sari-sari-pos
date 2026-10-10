import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api'
import WalletTopUpForm from '../components/WalletTopUpForm'
import { PESO, flattenErrors, formatTime } from '../utils'

const MONEY_OK = /^\d+(\.\d{1,2})?$/
const LABEL = { topup: 'Top-up', load_sent: 'Load sent', adjustment: 'Adjustment', reversal: 'Failed load restored',
                cash_in: 'Cash in', cash_out: 'Cash out' }

export default function OwnerWalletPage({ kind = 'load', title = 'Load wallet' }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    try {
      const response = await apiFetch(`/owner/wallet/?kind=${kind}`)
      if (response.ok) {
        setData(await response.json())
        setError('')
      } else if (response.status !== 401) {
        setError('Could not load the wallet. Please try again.')
      }
    } catch {
      setError('Cannot reach the server. Is Django running?')
    }
  }, [kind])

  useEffect(() => { load() }, [load])

  async function send(path, method, body, done) {
    try {
      const response = await apiFetch(path, { method, body: JSON.stringify(body) })
      if (response.ok) {
        setData(await response.json())
        setNotice(done)
        return ''
      }
      if (response.status === 400) return flattenErrors(await response.json()).join(' ')
      if (response.status === 401) return 'Your session ended. Please log in again.'
      return 'Something went wrong. Please try again.'
    } catch {
      return 'Cannot reach the server. Is Django running?'
    }
  }

  if (error) return <p style={{ color: 'crimson', fontSize: 18 }}>{error}</p>
  if (!data) return <p>Loading...</p>
  const { wallet, transactions } = data

  return (
    <div style={{ maxWidth: 1000 }}>
      <h1>{title}</h1>
      <div style={{ border: `2px solid ${wallet.is_low ? '#c0392b' : '#1b7f3b'}`, borderRadius: 8, padding: 16, maxWidth: 420 }}>
        <div style={{ color: '#555' }}>Balance the system expects</div>
        <div style={{ fontSize: 40, fontWeight: 'bold', color: wallet.is_low ? '#c0392b' : '#000' }}>{PESO}{wallet.balance}</div>
        {wallet.is_low && <b style={{ color: '#c0392b' }}>LOW. At or below {PESO}{wallet.low_level}. Time to top up.</b>}
        <p style={{ color: '#777', marginBottom: 0 }}>
          This is what the system calculated from every load and top-up. Compare it with the provider app.
          If they differ, use "Correct the balance" below.
        </p>
      </div>
      {notice && <p style={{ background: '#f3fbf5', border: '1px solid #1b7f3b', padding: 10, borderRadius: 6 }}>{notice}</p>}

      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', margin: '16px 0' }}>
        <div style={{ flex: '1 1 300px' }}>
          <WalletTopUpForm
            sources={[['owner_cash', "Owner's own money"], ['bank', 'Bank']]}
            onDone={(text) => { setNotice(text); load() }}
            kind={kind} title={title.toLowerCase()}
          />
        </div>
        <div style={{ flex: '1 1 300px', display: 'grid', gap: 16, alignContent: 'start' }}>
          <AdjustForm onSave={(actual, reason) => send(`/owner/wallet/adjust/?kind=${kind}`, 'POST', { actual_balance: actual, reason }, 'Balance corrected.')} />
          <LowForm current={wallet.low_level} onSave={(value) => send(`/owner/wallet/?kind=${kind}`, 'PATCH', { low_level: value }, 'Low-balance level saved.')} />
        </div>
      </div>

      <h2>Latest 50 wallet entries</h2>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 720 }}>
          <thead>
            <tr style={{ textAlign: 'left', borderBottom: '2px solid #333' }}>
              <th style={cell}>When (Manila)</th><th style={cell}>What</th><th style={cell}>Change</th>
              <th style={cell}>Balance after</th><th style={cell}>By</th><th style={cell}>Details</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((t) => (
              <tr key={t.id} style={{ borderBottom: '1px solid #ddd' }}>
                <td style={cell}>{formatTime(t.timestamp)}</td>
                <td style={cell}>{LABEL[t.type] ?? t.type}</td>
                <td style={{ ...cell, fontWeight: 'bold', color: parseFloat(t.amount) < 0 ? '#c0392b' : '#1b7f3b' }}>
                  {parseFloat(t.amount) > 0 ? '+' : ''}{t.amount}
                </td>
                <td style={cell}>{t.balance_after}</td>
                <td style={cell}>{t.user}</td>
                <td style={{ ...cell, fontSize: 13 }}>
                  {t.source && `from ${t.source}${t.amount_paid ? `, paid ${PESO}${t.amount_paid}` : ''}. `}
                  {t.reference_no && `ref ${t.reference_no}. `}{t.note}{t.shift && ` (shift #${t.shift})`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function AdjustForm({ onSave }) {
  const [actual, setActual] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)

  async function handleSubmit(event) {
    event.preventDefault()
    if (busyRef.current) return
    if (!MONEY_OK.test(actual)) return setError('Type the balance shown in the provider app (up to 2 decimals).')
    if (!reason.trim()) return setError('Enter the reason. It is required and permanent.')
    if (!window.confirm(`Set the wallet to ${PESO}${Number(actual).toFixed(2)}?\n\nThe difference is saved as an adjustment under your name.`)) return
    busyRef.current = true
    setBusy(true)
    const message = await onSave(actual, reason.trim())  
    busyRef.current = false
    setBusy(false)
    if (message) setError(message)
    else { setActual(''); setReason(''); setError('') }
  }

  return (
    <form onSubmit={handleSubmit} style={box}>
      <b>Correct the balance</b>
      <input style={field} inputMode="decimal" value={actual} onChange={(e) => setActual(e.target.value.replace(/[^\d.]/g, ''))}
             placeholder="Balance shown in the provider app" />
      <input style={field} maxLength={200} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (required)" />
      {error && <p style={{ color: 'crimson' }}>{error}</p>}
      <button type="submit" disabled={busy} style={{ padding: '8px 14px', marginTop: 6 }}>{busy ? 'Saving...' : 'Correct balance'}</button>
    </form>
  )
}

function LowForm({ current, onSave }) {
  const [value, setValue] = useState(current)
  const [error, setError] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()
    if (!MONEY_OK.test(value)) return setError('Enter an amount (up to 2 decimals).')
    const message = await onSave(value)
    setError(message)
  }

  return (
    <form onSubmit={handleSubmit} style={box}>
      <b>Low-balance alert level ({PESO})</b>
      <input style={field} inputMode="decimal" value={value} onChange={(e) => setValue(e.target.value.replace(/[^\d.]/g, ''))} />
      {error && <p style={{ color: 'crimson' }}>{error}</p>}
      <button type="submit" style={{ padding: '8px 14px', marginTop: 6 }}>Save level</button>
    </form>
  )
}

const cell = { padding: '8px 10px', verticalAlign: 'top' }
const box = { border: '1px solid #999', borderRadius: 8, padding: 14, background: '#fafafa' }
const field = { display: 'block', width: '100%', padding: 10, margin: '8px 0', fontSize: 16, boxSizing: 'border-box' }