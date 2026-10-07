import { useEffect, useState } from 'react'
import { apiFetch } from '../api'
import MovementList from '../components/MovementList'

export default function StockHistoryPage() {
  const [products, setProducts] = useState([])
  const [productId, setProductId] = useState('')
  const [type, setType] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    async function loadProducts() {
      try {
        const response = await apiFetch('/products/')
        if (response.ok) setProducts(await response.json())
        else if (response.status !== 401) setError('Could not load the product list.')
      } catch {
        setError('Cannot reach the server. Is Django running?')
      }
    }
    loadProducts()
  }, [])

  return (
    <div style={{ maxWidth: 1000 }}>
      <h1>Stock History</h1>
      <p style={{ color: '#555' }}>
        Every change to every product: sales, restocks, adjustments, and voids.
        This list is read-only, and nobody can edit or delete a line.
      </p>

      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', margin: '12px 0' }}>
        <label>
          Product{' '}
          <select style={select} value={productId} onChange={(e) => setProductId(e.target.value)}>
            <option value="">All products</option>
            {products.map((p) => (
              <option key={p.id} value={p.id}>{p.name}{!p.is_active && ' (inactive)'}</option>
            ))}
          </select>
        </label>
        <label>
          Type{' '}
          <select style={select} value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">All types</option>
            <option value="sale">Sale</option>
            <option value="restock">Restock</option>
            <option value="adjustment">Adjustment</option>
            <option value="void">Void</option>
          </select>
        </label>
      </div>
      {error && <p style={{ color: 'crimson' }}>{error}</p>}

      <MovementList key={`${productId}|${type}`} productId={productId} type={type} />
    </div>
  )
}

const select = { padding: 8, fontSize: 16 }