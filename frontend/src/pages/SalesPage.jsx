import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../api'
import ReceiptView from '../components/ReceiptView'
import { PESO, flattenErrors, formatTime, peso, toCents } from '../utils'
import { useCurrentShift } from '../useCurrentShift'

const QTY_OK = /^\d+(\.\d{1,3})?$/     
const CASH_OK = /^\d+(\.\d{1,2})?$/    
const num = (value) => String(parseFloat(value))   
function addQty(qty, amount) {
  const current = parseFloat(qty)
  if (Number.isNaN(current)) return String(amount)
  return String(Math.round((current + amount) * 1000) / 1000)
}

function estimateLineCents(unit, quantity) {
  let remaining = quantity
  let total = 0
  const tiers = [...unit.tiers].sort((a, b) => parseFloat(b.min_qty) - parseFloat(a.min_qty))
  for (const tier of tiers) {
    const size = parseFloat(tier.min_qty)
    const bundles = Math.floor(remaining / size + 1e-9)
    if (bundles > 0) {
      total += bundles * toCents(tier.price)
      remaining -= bundles * size
    }
  }
  return total + Math.round(remaining * toCents(unit.selling_price))
}

function SalesScreen({ shift }) {
  const [lines, setLines] = useState([])       
  const [held, setHeld] = useState(null)       
  const [scan, setScan] = useState('')
  const [picks, setPicks] = useState([])        
  const [scanMessage, setScanMessage] = useState('')
  const [cash, setCash] = useState('')
  const [saleError, setSaleError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState(null)    

  const scanRef = useRef(null)
  const latest = useRef(0)                     
  const submittingRef = useRef(false)         

  const focusScan = () => scanRef.current?.focus()
  useEffect(focusScan, [])

  function addUnit(product, unit) {
    setLines((prev) => {
      const index = prev.findIndex((l) => l.unitId === unit.id)
      if (index >= 0) {   
        return prev.map((l, i) =>
          i === index ? { ...l, product, qty: addQty(l.qty, 1) } : l
        )
      }
      return [...prev, { unitId: unit.id, product, qty: '1' }]
    })
  }

  async function handleScan(event) {
    event.preventDefault()
    const code = scan.trim()
    if (!code || submitting) return
    setScan('')
    setScanMessage('')
    const myRequest = ++latest.current

    try {
      const response = await apiFetch(`/products/lookup/?code=${encodeURIComponent(code)}`)
      if (response.status === 404) {
        setPicks([])
        setScanMessage('Item not found. Ask the owner to add it.')
        return
      }
      if (!response.ok) {
        if (response.status !== 401) setScanMessage('Something went wrong. Please try again.')
        return
      }
      const products = await response.json()

      for (const product of products) {
        const unit = product.units.find((u) => u.barcode === code)
        if (unit) {
          addUnit(product, unit)
          setPicks([])
          return
        }
      }
      if (myRequest === latest.current) setPicks(products)
    } catch {
      setScanMessage('Cannot reach the server. Is Django running?')
    }
  }

  function pickUnit(product, unit) {
    addUnit(product, unit)
    setPicks([])
    focusScan()
  }

  
  function setQty(unitId, value) {
    const cleaned = value.replace(/[^\d.]/g, '')   
    setLines((prev) => prev.map((l) => (l.unitId === unitId ? { ...l, qty: cleaned } : l)))
  }

  function removeLine(unitId) {
    setLines((prev) => prev.filter((l) => l.unitId !== unitId))
  }

  function changeUnit(oldId, newId) {
    setLines((prev) => {
      const line = prev.find((l) => l.unitId === oldId)
      const others = prev.filter((l) => l.unitId !== oldId)
      const existing = others.find((l) => l.unitId === newId)
      if (existing) {   
        return others.map((l) =>
          l.unitId === newId ? { ...l, qty: addQty(l.qty, parseFloat(line.qty) || 0) } : l
        )
      }
      return prev.map((l) => (l.unitId === oldId ? { ...l, unitId: newId } : l))
    })
  }

  function holdSale() {
    setHeld(lines)
    setLines([])
    setCash('')
    setSaleError('')
    focusScan()
  }
  function resumeSale() {
    setLines(held)
    setHeld(null)
    focusScan()
  }

  const computed = lines.map((l) => {
    const unit = l.product.units.find((u) => u.id === l.unitId)
    const valid = QTY_OK.test(l.qty) && parseFloat(l.qty) > 0
    return { ...l, unit, valid, cents: valid ? estimateLineCents(unit, parseFloat(l.qty)) : 0 }
  })
  const totalCents = computed.reduce((sum, l) => sum + l.cents, 0)
  const cashValid = CASH_OK.test(cash)
  const cashCents = cashValid ? toCents(cash) : 0
  const canComplete =
    computed.length > 0 && computed.every((l) => l.valid) &&
    cashValid && cashCents >= totalCents && !submitting

  async function completeSale() {
    if (!canComplete || submittingRef.current) return
    submittingRef.current = true
    setSubmitting(true)
    setSaleError('')

    try {
      const response = await apiFetch('/sales/', {
        method: 'POST',
        body: JSON.stringify({
          items: computed.map((l) => ({ product_unit: l.unitId, quantity: l.qty })),
          payment_type: 'cash',
          cash_received: (cashCents / 100).toFixed(2),
        }),
      })

      if (response.status === 201) {
        setResult(await response.json())   
        setLines([])
        setCash('')
        setPicks([])
      } else if (response.status === 400) {
        setSaleError(flattenErrors(await response.json()).join(' '))
      } else if (response.status !== 401) {
        setSaleError('Something went wrong. Check recent sales before trying again.')
      }
    } catch {
      setSaleError(
        'Connection lost. The sale may or may not have been saved. ' +
        'Do NOT press Complete again until you have checked with the owner.'
      )
    } finally {
      submittingRef.current = false
      setSubmitting(false)
    }
  }

  function closeReceipt() {
    setResult(null)
    setTimeout(focusScan, 0)
  }

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: 16, fontFamily: 'sans-serif' }}>
      <p><Link to="/">&larr; Back</Link></p>
      <h1 style={{ margin: '0 0 12px' }}>Sales</h1>
      {/* <p style={{ margin: '0 0 12px', color: '#555' }}>
        Shift #{shift.id} &middot; started {formatTime(shift.start_time)}
      </p> */}

      {/* <p style={{ margin: '0 0 12px', color: '#555' }}>
        Shift #{shift.id} &middot; started {formatTime(shift.start_time)} &middot;{' '}
        <Link to="/shift/end">End shift</Link>
      </p> */}
      <p style={{ margin: '0 0 12px', color: '#555' }}>
        Shift #{shift.id} &middot; started {formatTime(shift.start_time)} &middot;{' '}
        <Link to="/shift/summary">Summary / pay-outs</Link> &middot;{' '}
        <Link to="/shift/end">End shift</Link>
      </p>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        {/* LEFT: scan box and basket */}
        <div style={{ flex: '2 1 420px', minWidth: 0 }}>
          <form onSubmit={handleScan}>
            <input
              ref={scanRef}
              style={{ width: '100%', padding: 14, fontSize: 20, boxSizing: 'border-box' }}
              value={scan}
              onChange={(e) => setScan(e.target.value)}
              // Clicking empty space puts the cursor back. Clicking another field is allowed.
              onBlur={(e) => { if (!e.relatedTarget && !result) setTimeout(focusScan, 0) }}
              placeholder="Scan barcode or type item name, then Enter"
              autoComplete="off"
            />
          </form>
          {scanMessage && <p style={{ color: 'crimson', fontSize: 18 }}>{scanMessage}</p>}

          {picks.length > 0 && (
            <div style={{ border: '1px solid #ccc', borderRadius: 8, padding: 10, margin: '12px 0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <b>Pick an item</b>
                <button onClick={() => { setPicks([]); focusScan() }}>Close</button>
              </div>
              {picks.map((p) => (
                <div key={p.id} style={{ padding: '8px 0', borderTop: '1px solid #eee' }}>
                  {p.name}
                  {p.stock_status === 'out' && <small style={{ color: '#c0392b' }}> (out of stock)</small>}
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
                    {p.units.map((u) => (
                      <button key={u.id} style={{ padding: '8px 12px' }} onClick={() => pickUnit(p, u)}>
                        {u.unit_name} {PESO}{u.selling_price}
                      </button>
                    ))}
                    {p.units.length === 0 && <small>No selling units set up.</small>}
                  </div>
                </div>
              ))}
            </div>
          )}

          <div style={{ marginTop: 12 }}>
            {computed.length === 0 && <p style={{ color: '#777' }}>Basket is empty. Scan an item to begin.</p>}
            {computed.map((line) => (
              <BasketLine
                key={line.unitId}
                line={line}
                onQty={(v) => setQty(line.unitId, v)}
                onUnit={(newId) => changeUnit(line.unitId, newId)}
                onRemove={() => removeLine(line.unitId)}
                onDone={focusScan}
              />
            ))}
          </div>
        </div>

        {/* RIGHT: total, cash, complete */}
        <div style={{ flex: '1 1 280px', border: '1px solid #ccc', borderRadius: 8, padding: 16 }}>
          <div style={{ color: '#555' }}>Estimated total</div>
          <div style={{ fontSize: 38, fontWeight: 'bold' }}>{peso(totalCents)}</div>
          <small style={{ color: '#777' }}>The exact total is calculated by the server.</small>

          <label style={{ display: 'block', marginTop: 16 }}>
            Cash received
            <input
              style={{ display: 'block', width: '100%', padding: 12, fontSize: 20, boxSizing: 'border-box' }}
              inputMode="decimal"
              value={cash}
              onChange={(e) => setCash(e.target.value.replace(/[^\d.]/g, ''))}
              onKeyDown={(e) => { if (e.key === 'Enter') completeSale() }}
              placeholder="0.00"
            />
          </label>

          {cash && !cashValid && <p style={{ color: 'crimson' }}>Enter a valid amount (up to 2 decimals).</p>}
          {cashValid && lines.length > 0 && cashCents < totalCents && (
            <p style={{ color: 'crimson', fontSize: 18 }}>Short by {peso(totalCents - cashCents)}</p>
          )}
          {cashValid && lines.length > 0 && cashCents >= totalCents && (
            <p style={{ color: '#1b7f3b', fontSize: 22, fontWeight: 'bold' }}>
              Change: {peso(cashCents - totalCents)}
            </p>
          )}

          {saleError && <p style={{ color: 'crimson' }}>{saleError}</p>}

          <button
            onClick={completeSale}
            disabled={!canComplete}
            style={{ width: '100%', padding: 16, fontSize: 18, marginTop: 8 }}
          >
            {submitting ? 'Saving...' : 'Complete sale'}
          </button>

          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button onClick={holdSale} disabled={lines.length === 0 || held !== null} style={{ flex: 1, padding: 10 }}>
              Hold sale
            </button>
            {held && (
              <button onClick={resumeSale} disabled={lines.length > 0} style={{ flex: 1, padding: 10 }}>
                Resume held ({held.length})
              </button>
            )}
          </div>
          {held && lines.length > 0 && (
            <small style={{ color: '#777' }}>Finish or remove the current items to resume the held sale.</small>
          )}
        </div>
      </div>

      {/* The receipt, shown after a successful sale */}
      {result && (
        <div
          className="sale-overlay"
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', overflow: 'auto',
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
          }}
        >
          <div className="sale-panel" style={{ background: '#fff', borderRadius: 8, padding: 16, maxHeight: '95vh', overflow: 'auto' }}>
            {result.warnings.length > 0 && (
              <div style={{ background: '#fff3cd', padding: 10, borderRadius: 6, marginBottom: 10, maxWidth: 300 }}>
                {result.warnings.map((w) => <div key={w}>{w}</div>)}
              </div>
            )}
            <ReceiptView receipt={result.receipt} />
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button onClick={() => window.print()} style={{ flex: 1, padding: 12 }}>Print</button>
              <button onClick={closeReceipt} autoFocus style={{ flex: 1, padding: 12 }}>New sale</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}



function BasketLine({ line, onQty, onUnit, onRemove, onDone }) {
  const { product, unit, valid, cents } = line
  const needed = valid ? parseFloat(line.qty) * parseFloat(unit.pieces_per_unit) : 0
  const lowStock = valid && needed > parseFloat(product.stock_qty)

  return (
    <div style={{ border: '1px solid #ccc', borderRadius: 8, padding: 10, marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
        <b>{product.name}</b>
        <b>{valid ? peso(cents) : '-'}</b>
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          style={{
            width: 80, padding: 8, fontSize: 16,
            border: valid ? '1px solid #999' : '2px solid crimson',
          }}
          inputMode="decimal"
          value={line.qty}
          onChange={(e) => onQty(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') onDone() }}
        />
        {product.units.length > 1 ? (
          <select
            style={{ padding: 8, fontSize: 16 }}
            value={unit.id}
            onChange={(e) => { onUnit(Number(e.target.value)); onDone() }}
          >
            {product.units.map((u) => (
              <option key={u.id} value={u.id}>{u.unit_name} - {PESO}{u.selling_price}</option>
            ))}
          </select>
        ) : (
          <span>{unit.unit_name}</span>
        )}
        <span style={{ color: '#555' }}>@ {PESO}{unit.selling_price}</span>
        <button onClick={() => { onRemove(); onDone() }} style={{ marginLeft: 'auto', padding: 8 }}>
          Remove
        </button>
      </div>

      {!valid && <small style={{ color: 'crimson' }}>Enter a quantity above 0 (up to 3 decimals).</small>}
      {lowStock && (
        <small style={{ color: '#b86e00', display: 'block' }}>
          Stock shows only {num(product.stock_qty)} {product.base_unit}. You can still sell it, and the system will ask for a recount.
        </small>
      )}
    </div>
  )
}

export default function SalesPage() {
  const { loading, error, shift, isMine } = useCurrentShift()

  if (loading) return <p style={{ padding: 24, fontFamily: 'sans-serif' }}>Loading...</p>
  if (error) return <p style={{ padding: 24, fontFamily: 'sans-serif', color: 'crimson' }}>{error}</p>
  if (!shift || !isMine) return <NoShift shift={shift} />
  return <SalesScreen shift={shift} />
}

function NoShift({ shift }) {
  return (
    <div style={{ maxWidth: 520, margin: '0 auto', padding: 16, fontFamily: 'sans-serif' }}>
      <p><Link to="/">&larr; Back</Link></p>
      <h1>Sales</h1>
      {shift ? (
        <p style={{ background: '#fff3cd', padding: 14, borderRadius: 8 }}>
          <b>{shift.cashier}</b> has the shift open. You can sell only during your own shift.
          Please ask the owner.
        </p>
      ) : (
        <>
          <p style={{ background: '#fdecea', padding: 14, borderRadius: 8 }}>
            You need an open shift before you can sell.
          </p>
          <Link to="/shift/start" style={{ fontSize: 20 }}><b>Start shift</b></Link>
        </>
      )}
    </div>
  )
}