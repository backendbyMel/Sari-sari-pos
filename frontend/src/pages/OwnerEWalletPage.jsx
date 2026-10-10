import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api'
import { PESO, flattenErrors, formatTime } from '../utils'

const MONEY_OK = /^\d+(\.\d{1,2})?$/

export default function OwnerEWalletPage() {
  const [rules, setRules] = useState([])
  const [txs, setTxs] = useState([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [editing, setEditing] = useState(null)
  const [reversing, setReversing] = useState(null)

  const load = useCallback(async () => {
    try {
      const [r, t] = await Promise.all([apiFetch('/owner/fee-rules/'), apiFetch('/owner/ewallet/')])
      if (r.ok && t.ok) {
        setRules(await r.json())
        setTxs((await t.json()).transactions)
        setError('')
      } else if (r.status !== 401 && t.status !== 401) {
        setError('Could not load the GCash page. Please try again.')
      }
    } catch {
      setError('Cannot reach the server. Is Django running?')
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function send(path, method, body, done) {
    try {
      const response = await apiFetch(path, { method, body: body ? JSON.stringify(body) : undefined })
      if (response.ok) {
        setNotice(done)
        setEditing(null)
        setReversing(null)
        await load()
        return ''
      }
      if (response.status === 400) return flattenErrors(await response.json()).join(' ')
      if (response.status === 401) return 'Your session ended. Please log in again.'
      return 'Something went wrong. Please try again.'
    } catch {
      return 'Cannot reach the server. Is Django running?'
    }
  }

  async function removeRule(rule) {
    if (!window.confirm(`Remove the fee for ${PESO}${rule.min_amount} to ${PESO}${rule.max_amount}? Past transactions keep their fee.`)) return
    const message = await send(`/owner/fee-rules/${rule.id}/`, 'DELETE', null, 'Fee range removed.')
    if (message) setError(message)
  }

  return (
    <div style={{ maxWidth: 1100 }}>
      <h1>GCash fees and history</h1>
      {error && <p style={{ color: 'crimson', fontSize: 18 }}>{error}</p>}
      {notice && <p style={{ background: '#f3fbf5', border: '1px solid #1b7f3b', padding: 10, borderRadius: 6 }}>{notice}</p>}

      <h2>Fee table</h2>
      <p style={{ color: '#555' }}>
        The customer pays the fee in cash, for both cash in and cash out. Amounts are whole pesos and ranges cannot overlap.
        A sale outside every range makes the cashier enter a fee with a reason.
      </p>
      <table style={table}>
        <thead><tr style={head}><th style={cell}>From</th><th style={cell}>To</th><th style={cell}>Fee</th><th style={cell}></th></tr></thead>
        <tbody>
          {rules.map((r) => (editing === r.id
            ? <RuleEdit key={r.id} rule={r} onCancel={() => setEditing(null)} onSave={(body) => send(`/owner/fee-rules/${r.id}/`, 'PATCH', body, 'Fee range saved.')} />
            : (
              <tr key={r.id} style={{ borderBottom: '1px solid #ddd' }}>
                <td style={cell}>{PESO}{r.min_amount}</td><td style={cell}>{PESO}{r.max_amount}</td>
                <td style={cell}><b>{PESO}{r.fee}</b></td>
                <td style={cell}>
                  <button onClick={() => setEditing(r.id)} style={{ padding: '6px 10px' }}>Edit</button>{' '}
                  <button onClick={() => removeRule(r)} style={{ padding: '6px 10px' }}>Remove</button>
                </td>
              </tr>
            )))}
          {rules.length === 0 && <tr><td colSpan={4} style={{ ...cell, color: '#777' }}>No fees yet. Add a range below.</td></tr>}
        </tbody>
      </table>
      <AddRule onSave={(body) => send('/owner/fee-rules/', 'POST', body, 'Fee range added.')} />

      <h2 style={{ marginTop: 28 }}>Latest 50 transactions</h2>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ ...table, minWidth: 900 }}>
          <thead>
            <tr style={head}>
              <th style={cell}>When</th><th style={cell}>Cashier</th><th style={cell}>Type</th><th style={cell}>Amount</th>
              <th style={cell}>Fee</th><th style={cell}>Number / ref</th><th style={cell}>Status</th><th style={cell}></th>
            </tr>
          </thead>
          <tbody>
            {txs.map((t) => (
              <TxRow key={t.id} tx={t} reversing={reversing === t.id} onStart={() => { setReversing(t.id); setNotice('') }}
                     onCancel={() => setReversing(null)}
                     onReverse={(note) => send(`/owner/ewallet/${t.id}/reverse/`, 'POST', { note }, `${t.receipt_no} reversed. Return the cash and the GCash money by hand.`)} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function TxRow({ tx: t, reversing, onStart, onCancel, onReverse }) {
  return (
    <>
      <tr style={{ borderBottom: '1px solid #ddd', opacity: t.status === 'reversed' ? 0.55 : 1 }}>
        <td style={cell}>{formatTime(t.timestamp)}<br /><small>{t.receipt_no}</small></td>
        <td style={cell}>{t.cashier}<br /><small>shift #{t.shift}</small></td>
        <td style={cell}>{t.type === 'cash_in' ? 'Cash in' : 'Cash out'}</td>
        <td style={cell}>{PESO}{t.amount}</td>
        <td style={cell}>
          {PESO}{t.fee}
          {t.fee_overridden && (
            <div style={{ color: '#b86e00', fontSize: 13 }}>
              <b>DIFFERENT FEE</b> (table said {t.table_fee === null ? 'nothing' : `${PESO}${t.table_fee}`}): {t.fee_override_reason}
            </div>
          )}
        </td>
        <td style={cell}>{t.mobile}<br /><small>{t.reference_no}</small></td>
        <td style={cell}>{t.status === 'reversed' ? <b style={{ color: '#c0392b' }}>Reversed: {t.reversed_note}</b> : 'OK'}</td>
        <td style={cell}>{t.can_reverse && !reversing && <button onClick={onStart} style={{ padding: '6px 10px' }}>Reverse</button>}</td>
      </tr>
      {reversing && (
        <tr><td colSpan={8} style={{ padding: 10, background: '#fafafa' }}><ReverseForm tx={t} onSave={onReverse} onCancel={onCancel} /></td></tr>
      )}
    </>
  )
}

function ReverseForm({ tx, onSave, onCancel }) {
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)

  async function handleSubmit(event) {
    event.preventDefault()
    if (busyRef.current) return
    if (!note.trim()) return setError('Enter the reason. It is required and permanent.')
    const back = tx.type === 'cash_in' ? 'give the customer their cash back' : 'take the cash back from the customer'
    if (!window.confirm(`Reverse ${tx.receipt_no}?\n\nThe GCash wallet is restored and this transaction stops counting in the drawer. You must ${back} and return the GCash money in the app. It cannot be undone.`)) return
    busyRef.current = true
    setBusy(true)
    const message = await onSave(note.trim())  
    busyRef.current = false
    setBusy(false)
    if (message) setError(message)
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
      <input style={{ padding: 8, fontSize: 16, flex: 1, minWidth: 260 }} maxLength={200} value={note} autoFocus
             onChange={(e) => setNote(e.target.value)} placeholder="Reason for reversing (required)" />
      <button type="submit" disabled={busy} style={{ padding: '8px 14px' }}>{busy ? 'Saving...' : 'Reverse'}</button>
      <button type="button" onClick={onCancel} disabled={busy} style={{ padding: '8px 14px' }}>Cancel</button>
      {error && <span style={{ color: 'crimson', width: '100%' }}>{error}</span>}
    </form>
  )
}

function RuleEdit({ rule, onSave, onCancel }) {
  const [min, setMin] = useState(String(rule.min_amount))
  const [max, setMax] = useState(String(rule.max_amount))
  const [fee, setFee] = useState(rule.fee)
  const [error, setError] = useState('')
  async function save() {
    if (!/^\d+$/.test(min) || !/^\d+$/.test(max)) return setError('Amounts are whole pesos.')
    if (!MONEY_OK.test(fee)) return setError('Fee: up to 2 decimals.')
    setError(await onSave({ min_amount: Number(min), max_amount: Number(max), fee }))
  }
  return (
    <tr style={{ background: '#fafafa' }}>
      <td style={cell}><input style={small} inputMode="numeric" value={min} onChange={(e) => setMin(e.target.value.replace(/\D/g, ''))} /></td>
      <td style={cell}><input style={small} inputMode="numeric" value={max} onChange={(e) => setMax(e.target.value.replace(/\D/g, ''))} /></td>
      <td style={cell}><input style={small} inputMode="decimal" value={fee} onChange={(e) => setFee(e.target.value.replace(/[^\d.]/g, ''))} /></td>
      <td style={cell}>
        <button onClick={save} style={{ padding: '6px 10px' }}>Save</button>{' '}
        <button onClick={onCancel} style={{ padding: '6px 10px' }}>Cancel</button>
        {error && <div style={{ color: 'crimson' }}>{error}</div>}
      </td>
    </tr>
  )
}

function AddRule({ onSave }) {
  const [min, setMin] = useState('')
  const [max, setMax] = useState('')
  const [fee, setFee] = useState('')
  const [error, setError] = useState('')
  async function submit(event) {
    event.preventDefault()
    if (!/^\d+$/.test(min) || !/^\d+$/.test(max) || Number(min) < 1) return setError('Enter whole pesos for both amounts (from 1).')
    if (Number(max) < Number(min)) return setError('The upper amount must not be below the lower amount.')
    if (!MONEY_OK.test(fee)) return setError('Enter the fee (up to 2 decimals).')
    const message = await onSave({ min_amount: Number(min), max_amount: Number(max), fee })
    setError(message)
    if (!message) { setMin(''); setMax(''); setFee('') }
  }
  return (
    <form onSubmit={submit} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', margin: '10px 0' }}>
      <input style={small} inputMode="numeric" value={min} onChange={(e) => setMin(e.target.value.replace(/\D/g, ''))} placeholder="From" />
      <input style={small} inputMode="numeric" value={max} onChange={(e) => setMax(e.target.value.replace(/\D/g, ''))} placeholder="To" />
      <input style={small} inputMode="decimal" value={fee} onChange={(e) => setFee(e.target.value.replace(/[^\d.]/g, ''))} placeholder="Fee" />
      <button type="submit" style={{ padding: '8px 12px' }}>+ Add range</button>
      {error && <span style={{ color: 'crimson' }}>{error}</span>}
    </form>
  )
}

const table = { borderCollapse: 'collapse', width: '100%', minWidth: 460 }
const head = { textAlign: 'left', borderBottom: '2px solid #333' }
const cell = { padding: '8px 10px', verticalAlign: 'top' }
const small = { padding: 8, fontSize: 16, width: 110 }