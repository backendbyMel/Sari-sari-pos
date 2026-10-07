import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { apiFetch } from '../api'
import { PESO, flattenErrors, peso, toCents } from '../utils'

const QTY_OK = /^\d+(\.\d{1,3})?$/   
const MONEY_OK = /^\d+(\.\d{1,2})?$/  

const num = (value) => String(parseFloat(value))   

export default function ProductUnitsPage() {
  const { id } = useParams()                
  const [product, setProduct] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [panel, setPanel] = useState(null)  

  const load = useCallback(async () => {
    setError('')
    try {
      const response = await apiFetch(`/products/${id}/`)
      if (response.ok) {
        setProduct(await response.json())
      } else if (response.status === 404) {
        setError('Product not found.')
      } else if (response.status !== 401) {
        setError('Could not load this product. Please try again.')
      }
    } catch {
      setError('Cannot reach the server. Is Django running?')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  async function send(path, method, body) {
    try {
      const response = await apiFetch(path, {
        method,
        body: body ? JSON.stringify(body) : undefined,
      })
      if (response.ok) {
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

  async function saveUnit(payload) {
    const editing = panel?.mode === 'edit' ? panel.unit : null
    const message = editing
      ? await send(`/units/${editing.id}/`, 'PATCH', payload)
      : await send('/units/', 'POST', { ...payload, product: product.id })
    if (!message) setPanel(null)
    return message
  }

  function addTier(unit, minQty, price) {
    return send('/price-tiers/', 'POST', { product_unit: unit.id, min_qty: minQty, price })
  }

  async function removeTier(tier, unit) {
    const ok = window.confirm(
      `Remove the deal "${num(tier.min_qty)} ${unit.unit_name} for ${PESO}${tier.price}"?\n\n` +
      'Future sales go back to the normal price. Past receipts are not changed.'
    )
    if (!ok) return
    setActionError('')
    const message = await send(`/price-tiers/${tier.id}/`, 'DELETE')
    if (message) setActionError(message)
  }

  if (loading) return <p>Loading...</p>
  if (error) {
    return (
      <div>
        <p><Link to="/owner/products">&larr; Back to products</Link></p>
        <p style={{ color: 'crimson', fontSize: 18 }}>{error}</p>
      </div>
    )
  }

  const hasBaseUnit = product.units.some((u) => parseFloat(u.pieces_per_unit) === 1)
  const costPerBase = parseFloat(product.cost_price)

  return (
    <div style={{ maxWidth: 900 }}>
      <p><Link to="/owner/products">&larr; Back to products</Link></p>
      <h1 style={{ marginBottom: 4 }}>{product.name}</h1>
      <p style={{ marginTop: 0, color: '#555' }}>
        Stock is counted in <b>{product.base_unit}</b>. Current stock:{' '}
        <b>{num(product.stock_qty)} {product.base_unit}</b>.{' '}
        {!product.is_active && <b style={{ color: '#c0392b' }}>This product is inactive.</b>}
      </p>

      {product.units.length === 0 && (
        <p style={{ background: '#fdecea', padding: 10, borderRadius: 6 }}>
          This product has <b>no selling units</b>, so cashiers cannot sell it yet. Add its first unit below.
        </p>
      )}
      {product.units.length > 0 && !hasBaseUnit && (
        <p style={{ background: '#fff3cd', padding: 10, borderRadius: 6 }}>
          None of the units equals <b>1 {product.base_unit}</b>. That is allowed, but the restock
          margin warning and cost per piece work best when one unit is the base unit itself.
        </p>
      )}

      <button onClick={() => setPanel({ mode: 'add' })} disabled={panel !== null} style={{ padding: '10px 16px', fontSize: 16 }}>
        + Add unit
      </button>
      {actionError && <p style={{ color: 'crimson', fontSize: 16 }}>{actionError}</p>}

      {panel && (
        <UnitForm
          key={panel.mode === 'edit' ? panel.unit.id : 'new'}
          product={product}
          unit={panel.mode === 'edit' ? panel.unit : null}
          onSave={saveUnit}
          onCancel={() => setPanel(null)}
        />
      )}

      {product.units.map((unit) => {
        const pieces = parseFloat(unit.pieces_per_unit)
        const price = parseFloat(unit.selling_price)
        const costOfUnit = costPerBase * pieces
        const marginCents = Math.round((price - costOfUnit) * 100)
        return (
          <div key={unit.id} style={{ border: '1px solid #ccc', borderRadius: 8, padding: 14, margin: '16px 0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
              <div>
                <h2 style={{ margin: 0 }}>{unit.unit_name}</h2>
                <div style={{ color: '#555' }}>
                  {pieces === 1
                    ? `1 ${product.base_unit} (the base unit)`
                    : `${num(unit.pieces_per_unit)} ${product.base_unit} in one ${unit.unit_name}`}
                </div>
                <div style={{ color: '#555' }}>
                  Barcode: {unit.barcode ? <b>{unit.barcode}</b> : <i>none (found by name search)</i>}
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 26, fontWeight: 'bold' }}>{PESO}{unit.selling_price}</div>
                {pieces !== 1 && (
                  <small style={{ color: '#555' }}>
                    about {PESO}{(price / pieces).toFixed(2)} per {product.base_unit}
                  </small>
                )}
                <div>
                  <small style={{ color: marginCents < 0 ? '#c0392b' : '#555' }}>
                    {costPerBase > 0
                      ? `Cost about ${PESO}${costOfUnit.toFixed(2)} \u00B7 margin about ${peso(marginCents)}`
                      : 'No cost yet (record a restock first)'}
                  </small>
                </div>
              </div>
            </div>

            <div style={{ marginTop: 8 }}>
              <button onClick={() => setPanel({ mode: 'edit', unit })} disabled={panel !== null} style={{ padding: '6px 12px' }}>
                Edit barcode / price
              </button>
            </div>

            <div style={{ marginTop: 12, borderTop: '1px solid #eee', paddingTop: 10 }}>
              <b>Tingi deals</b>
              {unit.tiers.length === 0 && <div style={{ color: '#777' }}>No deals. Every {unit.unit_name} costs the normal price.</div>}
              {unit.tiers.map((tier) => (
                <div key={tier.id} style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '4px 0' }}>
                  <span>{num(tier.min_qty)} {unit.unit_name} for <b>{PESO}{tier.price}</b></span>
                  <button onClick={() => removeTier(tier, unit)} style={{ padding: '2px 8px' }}>Remove</button>
                </div>
              ))}
              <TierForm unit={unit} onAdd={(minQty, tierPrice) => addTier(unit, minQty, tierPrice)} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function UnitForm({ product, unit, onSave, onCancel }) {
  const isEdit = unit !== null
  const first = !isEdit && product.units.length === 0  

  const [unitName, setUnitName] = useState(unit?.unit_name ?? (first ? product.base_unit : ''))
  const [pieces, setPieces] = useState(unit ? num(unit.pieces_per_unit) : first ? '1' : '')
  const [barcode, setBarcode] = useState(unit?.barcode ?? '')
  const [price, setPrice] = useState(unit?.selling_price ?? '')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()   
    if (busy) return

    if (!unitName.trim()) return setError('Enter the unit name (for example stick, pack, or box).')
    if (!QTY_OK.test(pieces) || parseFloat(pieces) <= 0) {
      return setError(`Enter how many ${product.base_unit} are in one ${unitName.trim() || 'unit'} (more than 0, up to 3 decimals).`)
    }
    if (!MONEY_OK.test(price) || parseFloat(price) <= 0) {
      return setError('Enter a selling price above 0 (up to 2 decimals).')
    }

  
    const costOfUnit = parseFloat(product.cost_price) * parseFloat(pieces)
    if (costOfUnit > 0 && parseFloat(price) < costOfUnit) {
      const ok = window.confirm(
        `The price ${PESO}${price} is BELOW the average cost (about ${PESO}${costOfUnit.toFixed(2)}).\n\n` +
        'You would lose money on every sale. Save it anyway?'
      )
      if (!ok) return
    }
    setBusy(true)
    setError('')
    const cleanBarcode = barcode.trim()
    const payload = {
      barcode: cleanBarcode === '' ? null : cleanBarcode,
      selling_price: price,
    }
    if (!isEdit) {
      payload.unit_name = unitName.trim()
      payload.pieces_per_unit = pieces
    }

    const message = await onSave(payload)   
    if (message) {
      setError(message)
      setBusy(false)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      style={{ border: '1px solid #999', borderRadius: 8, padding: 16, margin: '16px 0', background: '#fafafa' }}
    >
      <h2 style={{ marginTop: 0 }}>{isEdit ? `Edit: ${unit.unit_name}` : 'Add unit'}</h2>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
        <label>
          Unit name {isEdit && '(locked)'}
          <input
            style={field}
            value={unitName}
            onChange={(e) => setUnitName(e.target.value)}
            disabled={isEdit}
            placeholder="stick, pack, box..."
            autoFocus={!isEdit}
          />
        </label>

        <label>
          {product.base_unit} in one {unitName.trim() || 'unit'} {isEdit && '(locked)'}
          <input
            style={field}
            inputMode="decimal"
            value={pieces}
            onChange={(e) => setPieces(e.target.value)}
            disabled={isEdit}
            placeholder="1, 20, 200..."
          />
          <small style={{ color: '#777' }}>
            {isEdit
              ? 'Locked: changing it would change how much stock each sale deducts.'
              : 'Selling one of these deducts this many from stock. Double-check it.'}
          </small>
        </label>

        <label>
          Barcode (optional)
          <input
            style={field}
            value={barcode}
            onChange={(e) => setBarcode(e.target.value)}
            placeholder="Click here, then scan"
            autoComplete="off"
            autoFocus={isEdit}
          />
          <small style={{ color: '#777' }}>Leave empty for loose items. They are found by name search.</small>
        </label>

        <label>
          Selling price ({PESO})
          <input style={field} inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} placeholder="0.00" />
          <small style={{ color: '#777' }}>The price of ONE of this unit.</small>
        </label>
      </div>

      {error && <p style={{ color: 'crimson', fontSize: 16 }}>{error}</p>}

      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <button type="submit" disabled={busy} style={{ padding: '10px 18px', fontSize: 16 }}>
          {busy ? 'Saving...' : isEdit ? 'Save changes' : 'Add unit'}
        </button>
        <button type="button" onClick={onCancel} disabled={busy} style={{ padding: '10px 18px', fontSize: 16 }}>
          Cancel
        </button>
      </div>
    </form>
  )
}

function TierForm({ unit, onAdd }) {
  const [minQty, setMinQty] = useState('')
  const [price, setPrice] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    if (busy) return

    if (!QTY_OK.test(minQty) || parseFloat(minQty) <= 1) {
      return setError('The quantity must be more than 1 (one item is just the normal price).')
    }
    if (!MONEY_OK.test(price) || parseFloat(price) <= 0) {
      return setError('Enter the bundle price (up to 2 decimals).')
    }

    const normalCents = Math.round(toCents(unit.selling_price) * parseFloat(minQty))
    if (toCents(price) >= normalCents) {
      const ok = window.confirm(
        `${minQty} ${unit.unit_name} for ${PESO}${price} is NOT cheaper than the normal price ` +
        `(${peso(normalCents)}).\n\nSave it anyway?`
      )
      if (!ok) return
    }

    setBusy(true)
    setError('')
    const message = await onAdd(minQty, price)
    setBusy(false)
    if (message) {
      setError(message)
    } else {
      setMinQty('')
      setPrice('')
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ marginTop: 8 }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          style={{ ...field, width: 90, margin: 0 }}
          inputMode="decimal"
          value={minQty}
          onChange={(e) => setMinQty(e.target.value)}
          placeholder="Qty"
          aria-label="Deal quantity"
        />
        <span>{unit.unit_name} for {PESO}</span>
        <input
          style={{ ...field, width: 110, margin: 0 }}
          inputMode="decimal"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          placeholder="Price"
          aria-label="Deal price"
        />
        <button type="submit" disabled={busy} style={{ padding: '8px 12px' }}>
          {busy ? 'Adding...' : 'Add deal'}
        </button>
      </div>
      {error && <div style={{ color: 'crimson', marginTop: 4 }}>{error}</div>}
    </form>
  )
}

const field = { display: 'block', width: '100%', padding: 10, marginTop: 4, fontSize: 16, boxSizing: 'border-box' }