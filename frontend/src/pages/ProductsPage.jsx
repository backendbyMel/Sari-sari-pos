import { useEffect, useState } from 'react'
import { apiFetch } from '../api'
import { PESO, flattenErrors } from '../utils'
import { Link } from 'react-router-dom'

const QTY_OK = /^\d+(\.\d{1,3})?$/
const num = (value) => String(parseFloat(value))   

const STATUS = {
  in_stock: { label: 'In stock', color: '#1b7f3b' },
  low: { label: 'Low', color: '#b86e00' },
  out: { label: 'Out', color: '#c0392b' },
}

export default function ProductsPage() {
  const [products, setProducts] = useState([])
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  const [panel, setPanel] = useState(null)  

  async function load() {
    setLoading(true)
    setError('')
    try {
      const [productRes, categoryRes] = await Promise.all([
        apiFetch('/products/'),
        apiFetch('/categories/'),
      ])
      if (productRes.ok && categoryRes.ok) {
        setProducts(await productRes.json())
        setCategories(await categoryRes.json())
      } else if (productRes.status !== 401 && categoryRes.status !== 401) {
        setError('Could not load products. Please try again.')
      }
    } catch {
      setError('Cannot reach the server. Is Django running?')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const categoryName = Object.fromEntries(categories.map((c) => [c.id, c.name]))

  async function saveProduct(payload) {
    const editing = panel?.mode === 'edit' ? panel.product : null
    try {
      const response = await apiFetch(
        editing ? `/products/${editing.id}/` : '/products/',
        { method: editing ? 'PATCH' : 'POST', body: JSON.stringify(payload) }
      )
      if (response.ok) {
        const saved = await response.json()
        setProducts((prev) =>
          editing
            ? prev.map((p) => (p.id === saved.id ? saved : p))
            : [...prev, saved].sort((a, b) => a.name.localeCompare(b.name))
        )
        setPanel(null)
        return ''
      }
      if (response.status === 400) return flattenErrors(await response.json()).join(' ')
      if (response.status === 401) return 'Your session ended. Please log in again.'
      return 'Something went wrong. Please try again.'
    } catch {
      return 'Cannot reach the server. Is Django running?'
    }
  }

  async function addCategory(name) {
    try {
      const response = await apiFetch('/categories/', {
        method: 'POST',
        body: JSON.stringify({ name }),
      })
      if (response.ok) {
        const created = await response.json()
        setCategories((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)))
        return { category: created }
      }
      if (response.status === 400) return { error: flattenErrors(await response.json()).join(' ') }
      return { error: 'Could not add the category.' }
    } catch {
      return { error: 'Cannot reach the server. Is Django running?' }
    }
  }

  async function toggleActive(product) {
    const next = !product.is_active
    if (!next) {
      const ok = window.confirm(
        `Deactivate "${product.name}"?\n\nIt can no longer be sold or restocked. ` +
        'Its history is kept, and you can reactivate it any time.'
      )
      if (!ok) return
    }
    setError('')
    try {
      const response = await apiFetch(`/products/${product.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: next }),
      })
      if (response.ok) {
        const saved = await response.json()
        setProducts((prev) => prev.map((p) => (p.id === saved.id ? saved : p)))
      } else if (response.status !== 401) {
        setError('Could not change the product. Please try again.')
      }
    } catch {
      setError('Cannot reach the server. Is Django running?')
    }
  }

  const term = search.trim().toLowerCase()
  const visible = products.filter(
    (p) => (showInactive || p.is_active) && p.name.toLowerCase().includes(term)
  )

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <h1 style={{ margin: 0 }}>Products</h1>
        <button onClick={() => setPanel({ mode: 'add' })} disabled={panel !== null} style={{ padding: '10px 16px', fontSize: 16 }}>
          + Add product
        </button>
      </div>

      {panel && (
        <ProductForm
          key={panel.mode === 'edit' ? panel.product.id : 'new'}
          product={panel.mode === 'edit' ? panel.product : null}
          categories={categories}
          onSave={saveProduct}
          onAddCategory={addCategory}
          onCancel={() => setPanel(null)}
        />
      )}

      <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap', margin: '16px 0' }}>
        <input
          style={{ padding: 10, fontSize: 16, minWidth: 220 }}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name"
        />
        <label>
          <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />{' '}
          Show inactive
        </label>
        <span style={{ color: '#777' }}>Showing {visible.length} of {products.length}</span>
      </div>

      {loading && <p>Loading...</p>}
      {error && <p style={{ color: 'crimson', fontSize: 18 }}>{error}</p>}
      {!loading && !error && visible.length === 0 && <p style={{ color: '#777' }}>No products to show.</p>}

      {visible.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 760 }}>
            <thead>
              <tr style={{ textAlign: 'left', borderBottom: '2px solid #333' }}>
                <th style={cell}>Name</th>
                <th style={cell}>Category</th>
                <th style={cell}>Stock</th>
                <th style={cell}>Cost per base unit</th>
                <th style={cell}>Low-stock level</th>
                <th style={cell}>Units and selling prices</th>
                <th style={cell}>Status</th>
                <th style={cell}></th>
              </tr>
            </thead>
            <tbody>
              {visible.map((p) => {
                const status = STATUS[p.stock_status] ?? STATUS.out
                return (
                  <tr key={p.id} style={{ borderBottom: '1px solid #ddd', opacity: p.is_active ? 1 : 0.5 }}>
                    <td style={cell}><b>{p.name}</b></td>
                    <td style={cell}>{p.category ? categoryName[p.category] ?? '-' : '-'}</td>
                    <td style={cell}>
                      <span style={{ color: status.color, fontWeight: 'bold' }}>
                        {num(p.stock_qty)} {p.base_unit}
                      </span>
                      <small style={{ display: 'block', color: status.color }}>{status.label}</small>
                      {p.needs_recount && <small style={{ display: 'block', color: '#b86e00' }}>Needs recount</small>}
                    </td>
                    <td style={cell}>{PESO}{p.cost_price}</td>
                    <td style={cell}>{num(p.low_stock_level)}</td>
                    <td style={cell}>
                      {p.units.length === 0
                        ? <small style={{ color: '#c0392b' }}>None yet (cannot be sold)</small>
                        : p.units.map((u) => (
                            <div key={u.id}>{u.unit_name} <b>{PESO}{u.selling_price}</b></div>
                          ))}
                    </td>
                    <td style={cell}>{p.is_active ? 'Active' : 'Inactive'}</td>
                    <td><Link
                        to={`/owner/products/${p.id}/units`}
                        style={{
                          padding: '6px 10px', border: '1px solid #767676', borderRadius: 3,
                          background: '#efefef', color: '#000', textDecoration: 'none', fontSize: 13.33,
                        }}
                      >
                        Prices / Units
                      </Link>{' '}</td>
                    <td style={{ ...cell, whiteSpace: 'nowrap' }}>
                      <button onClick={() => setPanel({ mode: 'edit', product: p })} style={{ padding: '6px 10px' }}>
                        Edit
                      </button>{' '}
                      <button onClick={() => toggleActive(p)} style={{ padding: '6px 10px' }}>
                        {p.is_active ? 'Deactivate' : 'Reactivate'}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

const cell = { padding: '8px 10px', verticalAlign: 'top' }

function ProductForm({ product, categories, onSave, onAddCategory, onCancel }) {
  const isEdit = product !== null
  const [name, setName] = useState(product?.name ?? '')
  const [category, setCategory] = useState(product?.category ? String(product.category) : '')
  const [baseUnit, setBaseUnit] = useState(product?.base_unit ?? '')
  const [low, setLow] = useState(product ? num(product.low_stock_level) : '0')
  const [newCategory, setNewCategory] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleAddCategory() {
    const trimmed = newCategory.trim()
    if (!trimmed) return
    const result = await onAddCategory(trimmed)
    if (result.error) {
      setError(result.error)
    } else {
      setCategory(String(result.category.id))   
      setNewCategory('')
      setError('')
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (busy) return
    const cleanName = name.trim()
    const cleanUnit = baseUnit.trim()

    if (!cleanName) {
      setError('Enter the product name.')
      return
    }
    if (!isEdit && !cleanUnit) {
      setError('Enter the base unit (the smallest thing you sell, like stick, sachet, or piece).')
      return
    }
    if (!QTY_OK.test(low)) {
      setError('Low-stock level must be a number (up to 3 decimals).')
      return
    }

    setBusy(true)
    setError('')
    const payload = {
      name: cleanName,
      category: category ? Number(category) : null,
      low_stock_level: low,
    }
    if (!isEdit) payload.base_unit = cleanUnit

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
      <h2 style={{ marginTop: 0 }}>{isEdit ? `Edit: ${product.name}` : 'Add product'}</h2>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
        <label>
          Name
          <input style={field} value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </label>

        <label>
          Base unit {isEdit && '(locked)'}
          <input
            style={field}
            value={baseUnit}
            onChange={(e) => setBaseUnit(e.target.value)}
            disabled={isEdit}
            placeholder="stick, sachet, piece..."
          />
          <small style={{ color: '#777' }}>
            {isEdit
              ? 'Cannot change: it would silently change what your stock numbers mean.'
              : 'The smallest thing you sell. Stock is counted in this unit.'}
          </small>
        </label>

        <label>
          Low-stock level
          <input style={field} inputMode="decimal" value={low} onChange={(e) => setLow(e.target.value)} />
          <small style={{ color: '#777' }}>In base units. At or below this, the item shows as Low.</small>
        </label>

        <label>
          Category
          <select style={field} value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">(none)</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <span style={{ display: 'flex', gap: 6, marginTop: 6 }}>
            <input
              style={{ ...field, margin: 0 }}
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()   
                  handleAddCategory()
                }
              }}
              placeholder="or type a new category"
            />
            <button type="button" onClick={handleAddCategory} style={{ padding: '0 12px' }}>Add</button>
          </span>
        </label>
      </div>

      {isEdit && (
        <p style={{ color: '#555' }}>
          Stock: <b>{num(product.stock_qty)} {product.base_unit}</b> and cost:{' '}
          <b>{PESO}{product.cost_price}</b> cannot be typed here. They change only through
          Restock and Stock Adjustments, so every change has a record.
        </p>
      )}
      {!isEdit && (
        <p style={{ color: '#555' }}>
          A new product starts with 0 stock. Add its selling units (with barcodes and prices) next,
          then record a restock to bring in the first stock.
        </p>
      )}

      {error && <p style={{ color: 'crimson', fontSize: 16 }}>{error}</p>}

      <div style={{ display: 'flex', gap: 8 }}>
        <button type="submit" disabled={busy} style={{ padding: '10px 18px', fontSize: 16 }}>
          {busy ? 'Saving...' : isEdit ? 'Save changes' : 'Create product'}
        </button>
                         
        <button type="button" onClick={onCancel} disabled={busy} style={{ padding: '10px 18px', fontSize: 16 }}>
          Cancel
        </button>
      </div>
    </form>
  )
}

const field = { display: 'block', width: '100%', padding: 10, marginTop: 4, fontSize: 16, boxSizing: 'border-box' }