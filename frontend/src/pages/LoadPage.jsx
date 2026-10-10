import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../api'
import ReceiptView from '../components/ReceiptView'
import WalletTopUpForm from '../components/WalletTopUpForm'
import { useCurrentShift } from '../useCurrentShift'
import { PESO, flattenErrors, formatTime, peso, toCents } from '../utils'

const MOBILE_OK = /^(09\d{9}|\+639\d{9}|639\d{9})$/
const REFERENCE_OK = /^[A-Za-z0-9-]{4,30}$/
const MONEY_OK = /^\d+(\.\d{1,2})?$/

function LoadScreen() {
  const [catalog, setCatalog] = useState([])
  const [loads, setLoads] = useState([])
  const [canTopUp, setCanTopUp] = useState(false)
  const [networkId, setNetworkId] = useState(null)
  const [product, setProduct] = useState(null)
  const [mobile, setMobile] = useState('')
  const [reference, setReference] = useState('')
  const [cash, setCash] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [failing, setFailing] = useState(null)  
  const busyRef = useRef(false)

  const reload = useCallback(async () => {
    try {
      const [cat, mine, settings] = await Promise.all([
        apiFetch('/load/products/'), apiFetch('/load/mine/'), apiFetch('/settings/public/'),
      ])
      if (cat.ok) setCatalog(await cat.json())
      if (mine.ok) setLoads((await mine.json()).loads)
      if (settings.ok) setCanTopUp((await settings.json()).cashier_can_topup)
    } catch {
      setError('Cannot reach the server. Is Django running?')
    }
  }, [])

  useEffect(() => { reload() }, [reload])

  const network = catalog.find((n) => n.id === networkId)
  const cleanMobile = mobile.replace(/[\s-]/g, '')
  const cashCents = MONEY_OK.test(cash) ? toCents(cash) : 0

  async function handleSend(event) {
    event.preventDefault()
    if (busyRef.current) return
    if (!product) return setError('Choose the network and the load.')
    if (!MOBILE_OK.test(cleanMobile)) return setError('Enter a mobile number like 0917 123 4567.')
    if (!REFERENCE_OK.test(reference)) return setError('Enter the reference number from the provider app (4 to 30 letters or digits).')
    const ok = window.confirm(
      `${network.name} ${product.name} (${PESO}${product.selling_price})\nto ${cleanMobile}\nReference: ${reference.toUpperCase()}\n\n` +
      'Record it ONLY if the load was already sent in the provider app and you collected the cash. Continue?'
    )
    if (!ok) return

    busyRef.current = true
    setBusy(true)
    setError('')
    setNotice('')
    try {
      
      const response = await apiFetch('/load/send/', {
        method: 'POST',
        body: JSON.stringify({ product: product.id, mobile_no: cleanMobile, reference_no: reference }),
      })
      if (response.status === 201) {
        setResult(await response.json())
        setProduct(null)
        setMobile('')
        setReference('')
        setCash('')
        await reload()
      } else if (response.status === 400) {
        setError(flattenErrors(await response.json()).join(' '))
      } else if (response.status !== 401) {
        setError('Something went wrong. Check the list below before recording it again.')
      }
    } catch {
      setError('Connection lost. The load may or may not have been saved. Check the list below BEFORE recording it again.')
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  async function markFailed(load, note) {
    try {
      const response = await apiFetch(`/load/${load.id}/fail/`, { method: 'POST', body: JSON.stringify({ note }) })
      if (response.ok) {
        const data = await response.json()
        setFailing(null)
        setNotice(`Marked failed. Give ${PESO}${data.refund} back to the customer.`)
        await reload()
        return ''
      }
      if (response.status === 400) return flattenErrors(await response.json()).join(' ')
      if (response.status === 401) return 'Your session ended. Please log in again.'
      return 'Something went wrong. Please try again.'
    } catch {
      return 'Cannot reach the server. Is Django running?'
    }
  }

  return (
    <div style={{ maxWidth: 560, margin: '0 auto', padding: 16, fontFamily: 'sans-serif' }}>
      <p><Link to="/">&larr; Back</Link></p>
      <h1>Mobile load</h1>
      {notice && <p style={{ background: '#f3fbf5', border: '1px solid #1b7f3b', padding: 10, borderRadius: 6 }}>{notice}</p>}

      <form onSubmit={handleSend}>
        <b>1. Network</b>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '6px 0 12px' }}>
          {catalog.map((n) => (
            <button type="button" key={n.id} disabled={n.id === networkId}
                    onClick={() => { setNetworkId(n.id); setProduct(null) }} style={{ padding: '10px 16px', fontSize: 16 }}>
              {n.name}
            </button>
          ))}
          {catalog.length === 0 && <span style={{ color: '#777' }}>No load products yet. Ask the owner to set them up.</span>}
        </div>

        {network && (
          <>
            <b>2. Load</b>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '6px 0 12px' }}>
              {network.products.map((p) => (
                <button type="button" key={p.id} disabled={product?.id === p.id}
                        onClick={() => setProduct(p)} style={{ padding: '10px 14px', fontSize: 16 }}>
                  {p.name}<br /><small>{PESO}{p.selling_price}</small>
                </button>
              ))}
            </div>
          </>
        )}

        {product && (
          <>
            <label style={{ display: 'block' }}>
              <b>3. Customer's mobile number</b>
              <input style={field} inputMode="tel" value={mobile} maxLength={16}
                     onChange={(e) => setMobile(e.target.value.replace(/[^\d+\s-]/g, ''))} placeholder="0917 123 4567" />
            </label>
            <p style={{ margin: '8px 0', fontSize: 20 }}>
              Collect <b>{PESO}{product.selling_price}</b> in cash
            </p>
            <label style={{ display: 'block' }}>
              Cash received (only to show the change)
              <input style={field} inputMode="decimal" value={cash}
                     onChange={(e) => setCash(e.target.value.replace(/[^\d.]/g, ''))} placeholder="0.00" />
            </label>
            {cash && MONEY_OK.test(cash) && cashCents >= toCents(product.selling_price) && (
              <p style={{ color: '#1b7f3b', fontSize: 22, fontWeight: 'bold' }}>
                Change: {peso(cashCents - toCents(product.selling_price))}
              </p>
            )}
            {cash && MONEY_OK.test(cash) && cashCents < toCents(product.selling_price) && (
              <p style={{ color: 'crimson' }}>Short by {peso(toCents(product.selling_price) - cashCents)}</p>
            )}
            <p style={{ color: '#555' }}>Now send the load in the provider app, then type its reference number:</p>
            <label style={{ display: 'block' }}>
              <b>4. Reference number</b>
              <input style={field} value={reference} maxLength={30} autoComplete="off"
                     onChange={(e) => setReference(e.target.value.replace(/[^A-Za-z0-9-]/g, ''))} />
            </label>
            {error && <p style={{ color: 'crimson', fontSize: 16 }}>{error}</p>}
            <button type="submit" disabled={busy} style={{ width: '100%', padding: 14, fontSize: 18, marginTop: 8 }}>
              {busy ? 'Saving...' : 'Record load sent'}
            </button>
          </>
        )}
        {!product && error && <p style={{ color: 'crimson', fontSize: 16 }}>{error}</p>}
      </form>

      <h2 style={{ marginTop: 28 }}>Loads this shift</h2>
      {loads.length === 0 && <p style={{ color: '#777' }}>None yet.</p>}
      {loads.map((l) => (
        <div key={l.id} style={{ borderBottom: '1px solid #ddd', padding: '8px 0', opacity: l.status === 'failed' ? 0.6 : 1 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <b>{l.network} {l.product} &middot; {l.mobile}</b>
            <b>{PESO}{l.price}</b>
          </div>
          <small style={{ color: '#555' }}>
            {l.receipt_no} &middot; ref {l.reference_no} &middot; {formatTime(l.timestamp)}
            {l.status === 'failed' && <b style={{ color: '#c0392b' }}> &middot; FAILED: {l.failed_note}</b>}
          </small>
          {l.status === 'success' && failing !== l.id && (
            <div><button onClick={() => { setFailing(l.id); setNotice('') }} style={{ marginTop: 4, padding: '4px 10px' }}>Mark failed</button></div>
          )}
          {failing === l.id && <FailForm load={l} onSave={(note) => markFailed(l, note)} onCancel={() => setFailing(null)} />}
        </div>
      ))}

      {canTopUp && (
        <div style={{ marginTop: 28 }}>
          <WalletTopUpForm sources={[['drawer', 'Cash from the drawer']]} onDone={(text) => { setNotice(text); reload() }} />
          <small style={{ color: '#777' }}>The money taken from the drawer is also saved as a pay-out in your shift.</small>
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

function FailForm({ load, onSave, onCancel }) {
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)

  async function handleSubmit(event) {
    event.preventDefault()
    if (busyRef.current) return
    if (!note.trim()) return setError('Enter what happened. It is required.')
    const ok = window.confirm(
      `Mark this load as FAILED?\n\nYou must give ${PESO}${load.price} back to the customer. ` +
      'The wallet is restored and this cannot be undone.'
    )
    if (!ok) return
    busyRef.current = true
    setBusy(true)
    const message = await onSave(note.trim()) 
    busyRef.current = false
    setBusy(false)
    if (message) setError(message)
  }

  return (
    <form onSubmit={handleSubmit} style={{ marginTop: 6 }}>
      <input style={{ ...field, margin: 0 }} maxLength={200} value={note} onChange={(e) => setNote(e.target.value)}
             placeholder="What happened? (required)" autoFocus />
      {error && <div style={{ color: 'crimson' }}>{error}</div>}
      <button type="submit" disabled={busy} style={{ marginTop: 6, padding: '6px 12px' }}>{busy ? 'Saving...' : 'Confirm failed'}</button>{' '}
      <button type="button" onClick={onCancel} disabled={busy} style={{ marginTop: 6, padding: '6px 12px' }}>Cancel</button>
    </form>
  )
}

export default function LoadPage() {
  const { loading, error, shift, isMine } = useCurrentShift()
  if (loading) return <p style={{ padding: 24, fontFamily: 'sans-serif' }}>Loading...</p>
  if (error) return <p style={{ padding: 24, fontFamily: 'sans-serif', color: 'crimson' }}>{error}</p>
  if (!shift || !isMine) {
    return (
      <div style={{ maxWidth: 520, margin: '0 auto', padding: 16, fontFamily: 'sans-serif' }}>
        <p><Link to="/">&larr; Back</Link></p>
        <h1>Mobile load</h1>
        <p style={{ background: '#fdecea', padding: 14, borderRadius: 8 }}>
          You need your own open shift to sell load. <Link to="/shift/start"><b>Start shift</b></Link>
        </p>
      </div>
    )
  }
  return <LoadScreen />
}

const field = { display: 'block', width: '100%', padding: 10, marginTop: 4, fontSize: 16, boxSizing: 'border-box' }