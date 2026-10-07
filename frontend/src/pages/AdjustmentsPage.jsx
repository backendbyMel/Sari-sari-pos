import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api'
import MovementList from '../components/MovementList'
import { flattenErrors } from '../utils'

const QTY_OK = /^\d+(\.\d{1,3})?$/  

const num = (value) => String(parseFloat(value))

const REASONS = [
  { value: 'damaged', label: 'Damaged', loss: true },
  { value: 'expired', label: 'Expired', loss: true },
  { value: 'stolen', label: 'Stolen / missing', loss: true },
  { value: 'count_error', label: 'Count error (after a recount)', loss: false },
]

export default function AdjustmentsPage() {
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [formKey, setFormKey] = useState(0)
  const [version, setVersion] = useState(0)
  const [historyProduct, setHistoryProduct] = useState('')  

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

  async function saveAdjustment(payload, before) {
    try {
      const response = await apiFetch('/stock-adjustments/', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      if (response.status === 201) {
        const data = await response.json()
        setResult({ ...data, before })
        await load()                       
        setVersion((v) => v + 1)           
        setFormKey((k) => k + 1)           
        return ''
      }
      if (response.status === 400) return flattenErrors(await response.json()).join(' ')
      if (response.status === 401) return 'Your session ended. Please log in again.'
      return 'Something went wrong. Check the history below before trying again.'
    } catch {
      return (
        'Connection lost. The adjustment may or may not have been saved. ' +
        'Check the history below BEFORE recording it again.'
      )
    }
  }

  return (
    <div style={{ maxWidth: 1000 }}>
      <h1>Stock Adjustments</h1>
      <p style={{ color: '#555' }}>
        Use this when the shelf and the computer disagree. Every adjustment needs a reason
        and is recorded under your name. It cannot be edited later. A mistake is fixed with another adjustment.
      </p>

      {loading && <p>Loading...</p>}
      {error && <p style={{ color: 'crimson', fontSize: 18 }}>{error}</p>}

      {result && (
        <div style={{ border: '2px solid #1b7f3b', borderRadius: 8, padding: 14, marginBottom: 16, background: '#f3fbf5' }}>
          <b style={{ color: '#1b7f3b' }}>Adjustment recorded: {result.product.name}</b>
          <div>
            Stock: {num(result.before.stock)} &rarr; <b>{num(result.product.stock_qty)}</b>
          </div>
          <div style={{ color: '#555' }}>{result.movement.reason}</div>
          {result.before.needsRecount && !result.product.needs_recount && (
            <div style={{ color: '#1b7f3b' }}>The "needs recount" flag was cleared.</div>
          )}
          <button onClick={() => setResult(null)} style={{ marginTop: 8, padding: '6px 12px' }}>Dismiss</button>
        </div>
      )}

      {!loading && !error && (
        <AdjustmentForm
          key={formKey}
          products={products}
          onSave={saveAdjustment}
          onProductChange={setHistoryProduct}
        />
      )}

      <h2 style={{ marginTop: 28 }}>
        Recent adjustments{historyProduct ? ' of this product' : ' (all products)'}
      </h2>
      <MovementList key={historyProduct} productId={historyProduct} type="adjustment" version={version} />
    </div>
  )
}

function AdjustmentForm({ products, onSave, onProductChange }) {
  const [productId, setProductId] = useState('')
  const [reason, setReason] = useState('damaged')
  const [direction, setDirection] = useState('minus')   // used only for "Count error"
  const [amount, setAmount] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)   

  const product = products.find((p) => String(p.id) === productId) ?? null
  const reasonInfo = REASONS.find((r) => r.value === reason)
  const isLoss = reasonInfo.loss

  const amountOk = QTY_OK.test(amount)
  const amountNum = amountOk ? parseFloat(amount) : 0
  const sign = isLoss || direction === 'minus' ? -1 : 1
  const delta = sign * amountNum
  const oldStock = product ? parseFloat(product.stock_qty) : 0
  const newStock = oldStock + delta
  const wouldGoNegative = product && amountOk && newStock < 0

  function chooseProduct(value) {
    setProductId(value)
    onProductChange(value)  
    setError('')
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (busyRef.current) return

    if (!product) return setError('Choose the product.')
    if (!amountOk) return setError(`Enter the amount in ${product.base_unit} (a number, up to 3 decimals).`)
    if (isLoss && amountNum <= 0) return setError('Enter an amount above 0.')
    if (!isLoss && amountNum === 0 && product.needs_recount === false) {
      return setError('An amount of 0 is only useful to clear a "needs recount" flag. Enter an amount above 0.')
    }
    if (wouldGoNegative) {
      return setError(`This would make stock negative (${num(newStock)}). Current stock is ${num(oldStock)}.`)
    }
    if (!note.trim()) return setError('Enter a reason or note. It is required and becomes part of the permanent record.')

    const summary =
      amountNum === 0
        ? 'Recounted: the system number is correct.'
        : `${delta < 0 ? 'Remove' : 'Add'} ${num(amountNum)} ${product.base_unit}.`
    const ok = window.confirm(
      `${product.name}\n${reasonInfo.label}: ${summary}\n` +
      `Stock ${num(oldStock)} -> ${num(newStock)} ${product.base_unit}\n\n` +
      'This is permanent and recorded under your name. Continue?'
    )
    if (!ok) return

    busyRef.current = true
    setBusy(true)
    setError('')
    const signedText = delta < 0 ? `-${amount}` : amount
    const payload = {
      product: product.id,
      quantity: amountNum === 0 ? '0' : signedText,
      reason_type: reason,
      note: note.trim(),
    }
    const message = await onSave(payload, { stock: product.stock_qty, needsRecount: product.needs_recount })
    busyRef.current = false
    if (message) {
      setError(message)
      setBusy(false)
    }
    
  }

  return (
    <form onSubmit={handleSubmit} style={{ border: '1px solid #999', borderRadius: 8, padding: 16, background: '#fafafa' }}>
      <h2 style={{ marginTop: 0 }}>Record an adjustment</h2>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
        <label>
          Product
          <select style={field} value={productId} onChange={(e) => chooseProduct(e.target.value)} autoFocus>
            <option value="">Choose...</option>
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({num(p.stock_qty)} {p.base_unit})
                {p.needs_recount && ' - NEEDS RECOUNT'}
                {!p.is_active && ' - inactive'}
              </option>
            ))}
          </select>
        </label>

        <label>
          Reason
          <select style={field} value={reason} onChange={(e) => setReason(e.target.value)}>
            {REASONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </label>

        {!isLoss && (
          <label>
            The recount found
            <select style={field} value={direction} onChange={(e) => setDirection(e.target.value)}>
              <option value="minus">LESS than the system says</option>
              <option value="plus">MORE than the system says</option>
            </select>
          </label>
        )}

        <label>
          {isLoss ? 'Amount lost' : 'Difference'} {product && `(in ${product.base_unit})`}
          <input
            style={field}
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder={isLoss ? 'How many were lost?' : 'How far off was the count?'}
          />
          <small style={{ color: '#777' }}>
            {isLoss
              ? 'Type a plain number. The system removes it from stock.'
              : 'Type 0 if you recounted and the system number was already right (this clears the recount flag).'}
          </small>
        </label>

        <label style={{ gridColumn: '1 / -1' }}>
          Note (required)
          <input
            style={field}
            maxLength={200}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="What happened? For example: pack fell in water"
          />
        </label>
      </div>

      {product && amountOk && (
        <div style={{ background: wouldGoNegative ? '#fdecea' : '#eef4ff', borderRadius: 6, padding: 12, marginTop: 16 }}>
          Stock: {num(oldStock)} &rarr; <b>{num(newStock)} {product.base_unit}</b>
          {wouldGoNegative && <div style={{ color: '#c0392b' }}>Stock cannot go below 0 through an adjustment.</div>}
        </div>
      )}

      {error && <p style={{ color: 'crimson', fontSize: 16 }}>{error}</p>}

      <button type="submit" disabled={busy} style={{ padding: '12px 20px', fontSize: 16, marginTop: 16 }}>
        {busy ? 'Saving...' : 'Record adjustment'}
      </button>
    </form>
  )
}

const field = { display: 'block', width: '100%', padding: 10, marginTop: 4, fontSize: 16, boxSizing: 'border-box' }