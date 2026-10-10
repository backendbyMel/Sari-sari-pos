import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../api'
import ReceiptView from '../components/ReceiptView'
import RequireOwnShift from '../components/RequireOwnShift'
import WalletTopUpForm from '../components/WalletTopUpForm'
import { PESO, flattenErrors, formatTime, peso, toCents } from '../utils'

const MOBILE_OK = /^(09\d{9}|\+639\d{9}|639\d{9})$/
const REFERENCE_OK = /^[A-Za-z0-9-]{4,30}$/
const MONEY_OK = /^\d+(\.\d{1,2})?$/

function EWalletScreen() {
  const [type, setType] = useState('cash_in')
  const [amount, setAmount] = useState('')
  const [quote, setQuote] = useState(null)
  const [mobile, setMobile] = useState('')
  const [reference, setReference] = useState('')
  const [differentFee, setDifferentFee] = useState(false)
  const [overrideFee, setOverrideFee] = useState('')
  const [overrideReason, setOverrideReason] = useState('')
  const [list, setList] = useState([])
  const [canTopUp, setCanTopUp] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const busyRef = useRef(false)
  const latest = useRef(0)   

  const reload = useCallback(async () => {
    try {
      const [mine, settings] = await Promise.all([apiFetch('/ewallet/mine/'), apiFetch('/settings/public/')])
      if (mine.ok) setList((await mine.json()).transactions)
      if (settings.ok) setCanTopUp((await settings.json()).cashier_can_topup)
    } catch {
      setError('Cannot reach the server. Is Django running?')
    }
  }, [])

  useEffect(() => { reload() }, [reload])

  useEffect(() => {
    if (!/^\d{1,7}$/.test(amount) || Number(amount) < 1) return undefined
    const mine = ++latest.current
    const timer = setTimeout(async () => {
      try {
        const response = await apiFetch(`/ewallet/quote/?amount=${amount}`)
        if (mine === latest.current && response.ok) setQuote(await response.json())
      } catch {
        // the fee line just stays empty
      }
    }, 250)
    return () => clearTimeout(timer)
  }, [amount])

  const amountOk = /^\d{1,7}$/.test(amount) && Number(amount) >= 1
  const tableFee = amountOk && quote && quote.amount === Number(amount) ? quote.fee : null
  const useOverride = differentFee && MONEY_OK.test(overrideFee)
  const fee = useOverride ? overrideFee : tableFee
  const amountCents = amountOk ? Number(amount) * 100 : 0
  const cashCents = fee === null ? null : type === 'cash_in' ? amountCents + toCents(fee) : amountCents - toCents(fee)
  const cleanMobile = mobile.replace(/[\s-]/g, '')
  const needsOverride = amountOk && quote && quote.amount === Number(amount) && tableFee === null

  async function handleSubmit(event) {
    event.preventDefault()
    if (busyRef.current) return
    if (!amountOk) return setError('Enter the amount in whole pesos.')
    if (fee === null) return setError('No fee is set for this amount. Tick "The fee is different" and enter the fee with a reason.')
    if (differentFee && !overrideReason.trim()) return setError('Enter the reason for the different fee. It is required and logged.')
    if (!MOBILE_OK.test(cleanMobile)) return setError('Enter a mobile number like 0917 123 4567.')
    if (!REFERENCE_OK.test(reference)) return setError('Enter the GCash reference number (4 to 30 letters or digits).')

    const word = type === 'cash_in' ? 'collect' : 'give'
    const ok = window.confirm(
      `${type === 'cash_in' ? 'CASH IN' : 'CASH OUT'} ${PESO}${Number(amount).toFixed(2)} (fee ${PESO}${fee})\n` +
      `Number: ${cleanMobile}\nReference: ${reference.toUpperCase()}\n\n` +
      `You ${word} ${peso(cashCents)} in cash. Record it only if the GCash transfer is done. Continue?`
    )
    if (!ok) return

    busyRef.current = true
    setBusy(true)
    setError('')
    setNotice('')
    // Notice: the fee is NOT sent unless it is a different fee with a reason.
    const body = { amount: Number(amount), mobile_no: cleanMobile, reference_no: reference }
    if (differentFee) {
      body.fee_override = overrideFee
      body.override_reason = overrideReason.trim()
    }
    try {
      const response = await apiFetch(`/ewallet/${type === 'cash_in' ? 'cash-in' : 'cash-out'}/`, {
        method: 'POST',
        body: JSON.stringify(body),
      })
      if (response.status === 201) {
        setResult(await response.json())
        setAmount('')
        setMobile('')
        setReference('')
        setDifferentFee(false)
        setOverrideFee('')
        setOverrideReason('')
        setQuote(null)
        await reload()
      } else if (response.status === 400) {
        setError(flattenErrors(await response.json()).join(' '))
      } else if (response.status !== 401) {
        setError('Something went wrong. Check the list below before recording it again.')
      }
    } catch {
      setError('Connection lost. It may or may not have been saved. Check the list below BEFORE recording it again.')
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  return (
    <div style={{ maxWidth: 560, margin: '0 auto', padding: 16, fontFamily: 'sans-serif' }}>
      <p><Link to="/">&larr; Back</Link></p>
      <h1>GCash cash in / out</h1>
      {notice && <p style={{ background: '#f3fbf5', border: '1px solid #1b7f3b', padding: 10, borderRadius: 6 }}>{notice}</p>}

      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <button type="button" onClick={() => setType('cash_in')} disabled={type === 'cash_in'} style={{ flex: 1, padding: 12, fontSize: 16 }}>
          Cash in
        </button>
        <button type="button" onClick={() => setType('cash_out')} disabled={type === 'cash_out'} style={{ flex: 1, padding: 12, fontSize: 16 }}>
          Cash out
        </button>
      </div>
      <p style={{ color: '#555', marginTop: 0 }}>
        {type === 'cash_in'
          ? 'The customer gives you cash, and you send GCash money to their number.'
          : 'The customer sends GCash money to the store, and you give them cash.'}
      </p>

      <form onSubmit={handleSubmit}>
        <label style={{ display: 'block' }}>
          <b>Amount (whole pesos)</b>
          <input style={field} inputMode="numeric" value={amount} autoFocus
                 onChange={(e) => setAmount(e.target.value.replace(/\D/g, '').slice(0, 7))} placeholder="500" />
        </label>

        {amountOk && (
          <div style={{ margin: '10px 0', fontSize: 18 }}>
            {fee === null && !needsOverride && <span style={{ color: '#777' }}>Checking the fee...</span>}
            {fee !== null && (
              <>
                Fee: <b>{PESO}{fee}</b>{useOverride && <span style={{ color: '#b86e00' }}> (different fee)</span>}
                <div style={{ fontSize: 24, marginTop: 4 }}>
                  {type === 'cash_in'
                    ? <>Collect <b>{peso(cashCents)}</b> in cash</>
                    : <>Give the customer <b>{peso(cashCents)}</b> in cash</>}
                </div>
              </>
            )}
            {needsOverride && (
              <div style={{ color: 'crimson' }}>No fee is set for this amount. Use "The fee is different" below.</div>
            )}
          </div>
        )}

        <label style={{ display: 'block', margin: '8px 0' }}>
          <input type="checkbox" checked={differentFee} onChange={(e) => setDifferentFee(e.target.checked)} />{' '}
          The fee is different (needs a reason, and the owner will see it)
        </label>
        {differentFee && (
          <div style={{ border: '1px solid #b86e00', borderRadius: 8, padding: 10, background: '#fffaf0' }}>
            <input style={field} inputMode="decimal" value={overrideFee} placeholder="Fee charged"
                   onChange={(e) => setOverrideFee(e.target.value.replace(/[^\d.]/g, ''))} />
            <input style={field} maxLength={200} value={overrideReason} placeholder="Reason (required)"
                   onChange={(e) => setOverrideReason(e.target.value)} />
          </div>
        )}

        <label style={{ display: 'block', marginTop: 10 }}>
          <b>Customer's mobile number</b>
          <input style={field} inputMode="tel" value={mobile} maxLength={16}
                 onChange={(e) => setMobile(e.target.value.replace(/[^\d+\s-]/g, ''))} placeholder="0917 123 4567" />
        </label>
        <p style={{ color: '#555', margin: '8px 0' }}>
          {type === 'cash_in'
            ? 'Collect the cash, send the GCash money in the app, then type the reference number.'
            : 'Check the GCash money arrived in the app, give the cash, then type the reference number.'}
        </p>
        <label style={{ display: 'block' }}>
          <b>GCash reference number</b>
          <input style={field} value={reference} maxLength={30} autoComplete="off"
                 onChange={(e) => setReference(e.target.value.replace(/[^A-Za-z0-9-]/g, ''))} />
        </label>

        {error && <p style={{ color: 'crimson', fontSize: 16 }}>{error}</p>}
        <button type="submit" disabled={busy} style={{ width: '100%', padding: 14, fontSize: 18, marginTop: 8 }}>
          {busy ? 'Saving...' : type === 'cash_in' ? 'Record cash in' : 'Record cash out'}
        </button>
      </form>

      <h2 style={{ marginTop: 28 }}>This shift</h2>
      {list.length === 0 && <p style={{ color: '#777' }}>None yet.</p>}
      {list.map((t) => (
        <div key={t.id} style={{ borderBottom: '1px solid #ddd', padding: '8px 0', opacity: t.status === 'reversed' ? 0.6 : 1 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <b>{t.type === 'cash_in' ? 'Cash in' : 'Cash out'} {PESO}{t.amount} &middot; {t.mobile}</b>
            <b>{t.type === 'cash_in' ? 'got' : 'gave'} {PESO}{t.cash}</b>
          </div>
          <small style={{ color: '#555' }}>
            {t.receipt_no} &middot; ref {t.reference_no} &middot; {formatTime(t.timestamp)}
            {t.status === 'reversed' && <b style={{ color: '#c0392b' }}> &middot; REVERSED: {t.reversed_note}</b>}
          </small>
        </div>
      ))}
      <small style={{ color: '#777' }}>Made a mistake? Ask the owner to reverse it. Only the owner can.</small>

      {canTopUp && (
        <div style={{ marginTop: 24 }}>
          <WalletTopUpForm kind="ewallet" title="GCash wallet" sources={[['drawer', 'Cash from the drawer']]}
                           onDone={(text) => { setNotice(text); reload() }} />
        </div>
      )}

      {result && (
        <div className="sale-overlay" style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', overflow: 'auto', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
          <div className="sale-panel" style={{ background: '#fff', borderRadius: 8, padding: 16, maxHeight: '95vh', overflow: 'auto' }}>
            {result.warnings.length > 0 && (
              <div style={{ background: '#fff3cd', padding: 10, borderRadius: 6, marginBottom: 10, maxWidth: 300 }}>
                {result.warnings.map((w) => <div key={w}>{w}</div>)}
              </div>
            )}
            <ReceiptView receipt={result.receipt} />
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button onClick={() => window.print()} style={{ flex: 1, padding: 12 }}>Print</button>
              <button onClick={() => setResult(null)} autoFocus style={{ flex: 1, padding: 12 }}>Done</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function EWalletPage() {
  return <RequireOwnShift title="GCash cash in / out"><EWalletScreen /></RequireOwnShift>
}

const field = { display: 'block', width: '100%', padding: 10, marginTop: 4, fontSize: 16, boxSizing: 'border-box' }