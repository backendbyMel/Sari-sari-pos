import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../api'
import CustomerPicker from '../components/CustomerPicker'
import ReceiptView from '../components/ReceiptView'
import { PESO, flattenErrors, formatTime, toCents } from '../utils'

const MONEY_OK = /^\d+(\.\d{1,2})?$/   

export default function CustomersPage() {
  const [selected, setSelected] = useState(null)
  return (
    <div style={{ maxWidth: 560, margin: '0 auto', padding: 16, fontFamily: 'sans-serif' }}>
      <p><Link to="/">&larr; Back</Link></p>
      <h1>Utang customers</h1>
      {!selected
        ? <CustomerPicker selected={null} onSelect={setSelected} onClear={() => {}} />
        : <CustomerDetail id={selected.id} onBack={() => setSelected(null)} />}
    </div>
  )
}

function CustomerDetail({ id, onBack }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [amount, setAmount] = useState('')
  const [payError, setPayError] = useState('')
  const [busy, setBusy] = useState(false)
  const [receipt, setReceipt] = useState(null)
  const busyRef = useRef(false)   

  const load = useCallback(async () => {
    try {
      const response = await apiFetch(`/customers/${id}/`)
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

  async function handlePay(event) {
    event.preventDefault()
    if (busyRef.current || !data) return
    if (!MONEY_OK.test(amount) || parseFloat(amount) <= 0) return setPayError('Enter the amount (more than 0, up to 2 decimals).')
    if (toCents(amount) > toCents(data.customer.balance)) {
      return setPayError(`That is more than the balance (${PESO}${data.customer.balance}).`)
    }
    const ok = window.confirm(
      `Take a payment of ${PESO}${Number(amount).toFixed(2)} from ${data.customer.name}?\n\n` +
      'The cash goes into your shift and it cannot be edited or deleted.'
    )
    if (!ok) return

    busyRef.current = true
    setBusy(true)
    setPayError('')
    try {
      const response = await apiFetch('/utang/payments/', {
        method: 'POST',
        body: JSON.stringify({ customer: id, amount }),
      })
      if (response.status === 201) {
        setReceipt((await response.json()).receipt)
        setAmount('')
        await load()
      } else if (response.status === 400) {
        setPayError(flattenErrors(await response.json()).join(' '))
      } else if (response.status !== 401) {
        setPayError('Something went wrong. Check the history below before trying again.')
      }
    } catch {
      setPayError('Connection lost. The payment may or may not have been saved. Check the history below BEFORE trying again.')
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  if (error) return <p style={{ color: 'crimson', fontSize: 18 }}>{error}</p>
  if (!data) return <p>Loading...</p>
  const { customer, history } = data
  const owes = toCents(customer.balance) > 0

  return (
    <div>
      <button onClick={onBack} style={{ padding: '6px 12px' }}>&larr; Other customers</button>
      <h2 style={{ marginBottom: 0 }}>{customer.name}</h2>
      <div style={{ color: '#555' }}>{customer.contact}</div>
      <div style={{ fontSize: 30, fontWeight: 'bold', margin: '8px 0' }}>Owes {PESO}{customer.balance}</div>
      <div style={{ color: '#555' }}>Credit limit {PESO}{customer.credit_limit}</div>

      {owes && (
        <form onSubmit={handlePay} style={{ border: '1px solid #999', borderRadius: 8, padding: 12, margin: '14px 0', background: '#fafafa' }}>
          <label>
            Payment received ({PESO})
            <input
              style={{ display: 'block', width: '100%', padding: 10, fontSize: 20, boxSizing: 'border-box', marginTop: 4 }}
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ''))}
              placeholder="0.00"
            />
          </label>
          <button type="button" onClick={() => setAmount(customer.balance)} style={{ marginTop: 6, padding: '4px 10px' }}>
            Pay in full ({PESO}{customer.balance})
          </button>
          {payError && <p style={{ color: 'crimson' }}>{payError}</p>}
          <button type="submit" disabled={busy} style={{ width: '100%', padding: 12, fontSize: 18, marginTop: 8 }}>
            {busy ? 'Saving...' : 'Record payment'}
          </button>
        </form>
      )}

      <h3>History</h3>
      {history.length === 0 && <p style={{ color: '#777' }}>Nothing yet.</p>}
      {history.map((h) => (
        <div key={`${h.kind}-${h.receipt_no}`} style={{ borderBottom: '1px solid #ddd', padding: '6px 0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <b style={{ color: h.kind === 'payment' ? '#1b7f3b' : h.kind === 'writeoff' ? '#b86e00' : '#000' }}>
              {h.kind === 'payment' ? 'Paid' : h.kind === 'writeoff' ? 'Written off' : 'Utang'} {PESO}{h.amount}
              {h.status === 'voided' && <span style={{ color: '#c0392b' }}> VOIDED</span>}
            </b>
            <span style={{ color: '#555' }}>{formatTime(h.timestamp)}</span>
          </div>
          <small style={{ color: '#555' }}>{h.receipt_no} &middot; balance after {PESO}{h.balance_after} &middot; {h.by}</small>
        </div>
      ))}

      {receipt && (
        <div
          className="sale-overlay"
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', overflow: 'auto', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}
        >
          <div className="sale-panel" style={{ background: '#fff', borderRadius: 8, padding: 16, maxHeight: '95vh', overflow: 'auto' }}>
            <ReceiptView receipt={receipt} />
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button onClick={() => window.print()} style={{ flex: 1, padding: 12 }}>Print</button>
              <button onClick={() => setReceipt(null)} autoFocus style={{ flex: 1, padding: 12 }}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}