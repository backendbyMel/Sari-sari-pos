import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api'
import { PESO, flattenErrors } from '../utils'

const QTY_OK = /^\d+(\.\d{1,3})?$/     
const COST_OK = /^\d+(\.\d{1,4})?$/    

const num = (value) => String(parseFloat(value))              
const money = (value, places = 2) => PESO + Number(value).toFixed(places)   
const todayText = () => new Date().toLocaleDateString('en-CA') 

export default function RestockPage() {
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)      
  const [formKey, setFormKey] = useState(0)        
  const [historyVersion, setHistoryVersion] = useState(0)

  const load = useCallback(async () => {
    try {
      const response = await apiFetch('/products/')
      if (response.ok) {
        setProducts(await response.json())
        setError('')
      } else if (response.status !== 401) {
        setError('Could not load products. Please try again.')
      }
    } catch {
      setError('Cannot reach the server. Is Django running?')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const sellable = products.filter((p) => p.is_active && p.units.length > 0)

  async function saveRestock(payload, before) {
    try {
      const response = await apiFetch('/restocks/', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      if (response.status === 201) {
        const data = await response.json()
        setResult({ ...data, before })           
        await load()                              
        setHistoryVersion((v) => v + 1)
        setFormKey((k) => k + 1)                
        return ''
      }
      if (response.status === 400) return flattenErrors(await response.json()).join(' ')
      if (response.status === 401) return 'Your session ended. Please log in again.'
      return 'Something went wrong. Check the history below before trying again.'
    } catch {
      return (
        'Connection lost. The delivery may or may not have been saved. ' +
        'Check the history below BEFORE recording it again.'
      )
    }
  }

  return (
    <div style={{ maxWidth: 860 }}>
      <h1>Restock</h1>

      {loading && <p>Loading...</p>}
      {error && <p style={{ color: 'crimson', fontSize: 18 }}>{error}</p>}

      {result && <ResultCard result={result} onClose={() => setResult(null)} />}

      {!loading && !error && (
        <RestockForm key={formKey} products={sellable} onSave={saveRestock} historyVersion={historyVersion} />
      )}
    </div>
  )
}
function ResultCard({ result, onClose }) {
  const { product, restock, warnings, before } = result
  return (
    <div style={{ border: '2px solid #1b7f3b', borderRadius: 8, padding: 14, marginBottom: 16, background: '#f3fbf5' }}>
      <b style={{ color: '#1b7f3b' }}>Delivery recorded: {product.name}</b>
      <div>
        Added <b>{num(restock.quantity)}</b>. Stock: {num(before.stock)} &rarr; <b>{num(product.stock_qty)}</b>
      </div>
      <div>
        Average cost per base unit: {money(product.old_cost_price, 4)} &rarr;{' '}
        <b>{money(product.new_cost_price, 4)}</b>
      </div>
      {warnings.map((w) => (
        <div key={w} style={{ background: '#fff3cd', padding: 8, borderRadius: 6, marginTop: 8 }}>
          <b>Warning:</b> {w}
        </div>
      ))}
      <button onClick={onClose} style={{ marginTop: 8, padding: '6px 12px' }}>Dismiss</button>
    </div>
  )
}
function RestockForm({ products, onSave, historyVersion }) {
  const [productId, setProductId] = useState('')
  const [unitId, setUnitId] = useState('')
  const [qty, setQty] = useState('')
  const [cost, setCost] = useState('')
  const [date, setDate] = useState(todayText())
  const [receiptNo, setReceiptNo] = useState('')
  const [expiry, setExpiry] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)    

  const product = products.find((p) => String(p.id) === productId) ?? null
  const unit = product?.units.find((u) => String(u.id) === unitId) ?? null

  const qtyValid = QTY_OK.test(qty) && parseFloat(qty) > 0
  const costValid = COST_OK.test(cost) && parseFloat(cost) > 0
  let preview = null
  if (product && unit && qtyValid && costValid) {
    const pieces = parseFloat(unit.pieces_per_unit)
    const baseQty = parseFloat(qty) * pieces
    const costPerBase = parseFloat(cost) / pieces
    const oldStock = parseFloat(product.stock_qty)
    const oldCost = parseFloat(product.cost_price)
    const counted = Math.max(oldStock, 0)     
    const newCost = (counted * oldCost + baseQty * costPerBase) / (counted + baseQty)

    const smallest = [...product.units].sort(
      (a, b) => parseFloat(a.pieces_per_unit) - parseFloat(b.pieces_per_unit)
    )[0]
    const pricePerBase = parseFloat(smallest.selling_price) / parseFloat(smallest.pieces_per_unit)
    const marginBefore = pricePerBase - oldCost
    const marginAfter = pricePerBase - newCost

    preview = {
      baseQty, costPerBase, oldStock, newStock: oldStock + baseQty, oldCost, newCost,
      marginDrops: oldCost > 0 && marginAfter < marginBefore, marginBefore, marginAfter,
    }
  }

  function chooseProduct(value) {
    setProductId(value)
    setUnitId('')        
    setError('')
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (busyRef.current) return

    if (!product) return setError('Choose the product.')
    if (!unit) return setError('Choose the unit you received (for example box, pack, or piece).')
    if (!qtyValid) return setError('Enter the quantity received (more than 0, up to 3 decimals).')
    if (!costValid) return setError(`Enter the cost of ONE ${unit.unit_name} (more than 0, up to 4 decimals).`)
    if (!date) return setError('Enter the delivery date.')
    if (expiry && expiry < date) return setError('The expiry date cannot be before the delivery date.')

    const oldCost = parseFloat(product.cost_price)
    if (preview && oldCost > 0) {
      const ratio = preview.costPerBase / oldCost
      if (ratio > 1.5 || ratio < 0.5) {
        const ok = window.confirm(
          `This works out to ${money(preview.costPerBase, 4)} per ${product.base_unit}, ` +
          `but the current average cost is ${money(oldCost, 4)}.\n\n` +
          `Did you enter the cost of ONE ${unit.unit_name}?\n\nRecord it anyway?`
        )
        if (!ok) return
      }
    }

    busyRef.current = true
    setBusy(true)
    setError('')
    const payload = {
      product: product.id,
      product_unit: unit.id,
      quantity: qty,
      unit_cost: cost,
      date,
      delivery_receipt_no: receiptNo.trim(),
      expiry_date: expiry === '' ? null : expiry,
    }
    const message = await onSave(payload, { stock: product.stock_qty })   // '' means saved
    busyRef.current = false
    if (message) {
      setError(message)
      setBusy(false)
    }
    
  }

  return (
    <>
      <form
        onSubmit={handleSubmit}
        style={{ border: '1px solid #999', borderRadius: 8, padding: 16, background: '#fafafa' }}
      >
        <h2 style={{ marginTop: 0 }}>Record a delivery</h2>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
          <label>
            Product
            <select style={field} value={productId} onChange={(e) => chooseProduct(e.target.value)} autoFocus>
              <option value="">Choose...</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({num(p.stock_qty)} {p.base_unit} in stock)
                </option>
              ))}
            </select>
          </label>

          <label>
            Unit received
            <select style={field} value={unitId} onChange={(e) => setUnitId(e.target.value)} disabled={!product}>
              <option value="">Choose...</option>
              {product?.units.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.unit_name}
                  {parseFloat(u.pieces_per_unit) !== 1 && ` (${num(u.pieces_per_unit)} ${product.base_unit})`}
                </option>
              ))}
            </select>
          </label>

          <label>
            Quantity received
            <input
              style={field}
              inputMode="decimal"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              placeholder={unit ? `How many ${unit.unit_name}?` : ''}
            />
          </label>

          <label>
            Cost of ONE {unit ? unit.unit_name : 'unit'} ({PESO})
            <input
              style={field}
              inputMode="decimal"
              value={cost}
              onChange={(e) => setCost(e.target.value)}
              placeholder="What you paid for one"
            />
          </label>

          <label>
            Delivery date
            <input style={field} type="date" value={date} max={todayText()} onChange={(e) => setDate(e.target.value)} />
          </label>

          <label>
            Delivery receipt no. (optional)
            <input style={field} maxLength={50} value={receiptNo} onChange={(e) => setReceiptNo(e.target.value)} />
          </label>

          <label>
            Expiry date (optional)
            <input style={field} type="date" value={expiry} min={date} onChange={(e) => setExpiry(e.target.value)} />
          </label>
        </div>

        {preview && (
          <div style={{ background: '#eef4ff', borderRadius: 6, padding: 12, margin: '16px 0 0' }}>
            <b>Preview (estimate, the server calculates the exact figures)</b>
            <div>
              You are receiving {num(qty)} {unit.unit_name} = <b>{num(preview.baseQty)} {product.base_unit}</b>
            </div>
            <div>Cost per {product.base_unit}: <b>{money(preview.costPerBase, 4)}</b></div>
            <div>Stock: {num(preview.oldStock)} &rarr; <b>{num(preview.newStock)} {product.base_unit}</b></div>
            <div>
              Average cost per {product.base_unit}: {money(preview.oldCost, 4)} &rarr;{' '}
              <b>{money(preview.newCost, 4)}</b>
            </div>
            {preview.marginDrops && (
              <div style={{ color: '#b86e00', marginTop: 4 }}>
                Margin would drop from {money(preview.marginBefore)} to {money(preview.marginAfter)} per {product.base_unit}.
              </div>
            )}
          </div>
        )}

        {error && <p style={{ color: 'crimson', fontSize: 16 }}>{error}</p>}

        <button type="submit" disabled={busy} style={{ padding: '12px 20px', fontSize: 16, marginTop: 16 }}>
          {busy ? 'Saving...' : 'Record delivery'}
        </button>
      </form>

      {product && <RestockHistory productId={product.id} baseUnit={product.base_unit} version={historyVersion} />}
    </>
  )
}

function RestockHistory({ productId, baseUnit, version }) {
  const [rows, setRows] = useState([])
  const [message, setMessage] = useState('')
  const latest = useRef(0)    

  useEffect(() => {
    const myRequest = ++latest.current
    async function loadHistory() {
      try {
        const response = await apiFetch(`/restocks/?product=${productId}`)
        if (myRequest !== latest.current) return
        if (response.ok) {
          const data = await response.json()
          setRows(Array.isArray(data) ? data : data.results ?? [])
          setMessage('')
        } else if (response.status !== 401) {
          setRows([])
          setMessage('Could not load the delivery history.')
        }
      } catch {
        if (myRequest === latest.current) {
          setRows([])
          setMessage('Cannot reach the server.')
        }
      }
    }
    loadHistory()
  }, [productId, version])

  return (
    <div style={{ marginTop: 24 }}>
      <h2>Recent deliveries of this product</h2>
      {message && <p style={{ color: 'crimson' }}>{message}</p>}
      {!message && rows.length === 0 && <p style={{ color: '#777' }}>No deliveries recorded yet.</p>}
      {rows.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 560 }}>
            <thead>
              <tr style={{ textAlign: 'left', borderBottom: '2px solid #333' }}>
                <th style={cell}>Date</th>
                <th style={cell}>Quantity ({baseUnit})</th>
                <th style={cell}>Cost per {baseUnit}</th>
                <th style={cell}>Delivery receipt</th>
                <th style={cell}>Expiry</th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 10).map((r) => (
                <tr key={r.id} style={{ borderBottom: '1px solid #ddd' }}>
                  <td style={cell}>{r.date}</td>
                  <td style={cell}>{num(r.quantity)}</td>
                  <td style={cell}>{PESO}{r.unit_cost}</td>
                  <td style={cell}>{r.delivery_receipt_no || '-'}</td>
                  <td style={cell}>{r.expiry_date || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

const field = { display: 'block', width: '100%', padding: 10, marginTop: 4, fontSize: 16, boxSizing: 'border-box' }
const cell = { padding: '8px 10px', verticalAlign: 'top' }