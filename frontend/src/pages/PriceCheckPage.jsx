import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../api'

const STATUS = {
  in_stock: { label: 'In stock', color: '#1b7f3b' },
  low: { label: 'Low stock', color: '#b86e00' },
  out: { label: 'Out of stock', color: '#c0392b' },
}


const num = (value) => String(parseFloat(value))

export default function PriceCheckPage() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [searched, setSearched] = useState('')   
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)

  const inputRef = useRef(null)    
  const latest = useRef(0)        

  useEffect(() => {
    inputRef.current?.focus()     
  }, [])

  async function handleSubmit(event) {
    event.preventDefault()         
    const code = query.trim()
    if (!code) return

    const myRequest = ++latest.current
    setLoading(true)
    setMessage('')

    try {
      const response = await apiFetch(`/products/lookup/?code=${encodeURIComponent(code)}`)
      if (myRequest !== latest.current) return      
      if (response.ok) {
        setResults(await response.json())
        setSearched(code)
      } else if (response.status === 404) {
        setResults([])
        setMessage('Item not found. Ask the owner to add it.')
      } else if (response.status !== 401) {         
        setResults([])
        setMessage('Something went wrong. Please try again.')
      }
    } catch {
      if (myRequest === latest.current) {
        setResults([])
        setMessage('Cannot reach the server. Is Django running?')
      }
    } finally {
      if (myRequest === latest.current) setLoading(false)
      inputRef.current?.focus()
      inputRef.current?.select()   // next scan or typing replaces the old text
    }
  }

  return (
    <div style={{ maxWidth: 640, margin: '0 auto', padding: 16, fontFamily: 'sans-serif' }}>
      <p><Link to="/">&larr; Back</Link></p>
      <h1>Price Check</h1>

      <form onSubmit={handleSubmit}>
        <input
          ref={inputRef}
          style={{ width: '100%', padding: 14, fontSize: 20, boxSizing: 'border-box' }}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Scan barcode or type item name, then press Enter"
          autoComplete="off"
        />
      </form>

      <p style={{ minHeight: 24, color: '#555' }}>
        {loading ? 'Searching...' : searched && results.length > 0 ? `Results for "${searched}"` : ''}
      </p>
      {message && <p style={{ color: 'crimson', fontSize: 18 }}>{message}</p>}

      {results.map((product) => (
        <ProductCard key={product.id} product={product} scanned={searched} />
      ))}
    </div>
  )
}

function ProductCard({ product, scanned }) {
  const status = STATUS[product.stock_status] ?? STATUS.out

  return (
    <div style={{ border: '1px solid #ccc', borderRadius: 8, padding: 16, marginBottom: 16 }}>
      <h2 style={{ margin: '0 0 4px' }}>{product.name}</h2>
      <p style={{ margin: '0 0 12px', fontSize: 18, color: status.color, fontWeight: 'bold' }}>
        {status.label} ({num(product.stock_qty)} {product.base_unit})
      </p>

      {product.units.length === 0 && <p>No selling units set up yet.</p>}

      {product.units.map((unit) => {
        const isScanned = unit.barcode && unit.barcode === scanned  
        return (
          <div
            key={unit.id}
            style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
              padding: '8px 10px', borderRadius: 6,
              background: isScanned ? '#fff6c8' : 'transparent',
            }}
          >
            <span>
              <b>{unit.unit_name}</b>
              {parseFloat(unit.pieces_per_unit) !== 1 &&
                ` (${num(unit.pieces_per_unit)} ${product.base_unit})`}
              {unit.tiers.map((tier) => (
                <small key={tier.id} style={{ display: 'block', color: '#555' }}>
                  {num(tier.min_qty)} for &#8369;{tier.price}
                </small>
              ))}
            </span>
            <span style={{ fontSize: 22, fontWeight: 'bold' }}>&#8369;{unit.selling_price}</span>
          </div>
        )
      })}
    </div>
  )
}