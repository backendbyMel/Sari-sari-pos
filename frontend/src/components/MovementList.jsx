import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api'

const PAGE_SIZE = 50  
const num = (value) => String(parseFloat(value))
const signed = (value) => {
  const n = parseFloat(value)
  return (n > 0 ? '+' : '') + String(n)
}

const TYPE_LABEL = {
  sale: 'Sale',
  restock: 'Restock',
  adjustment: 'Adjustment',
  void: 'Void',
  breakdown: 'Breakdown',
}

const when = (iso) =>
  new Date(iso).toLocaleString('en-PH', { timeZone: 'Asia/Manila', dateStyle: 'medium', timeStyle: 'short' })

export default function MovementList({ productId = '', type = '', version = 0 }) {
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(true)
  const latest = useRef(0) 

  useEffect(() => {
    const myRequest = ++latest.current
    async function run() {
      setLoading(true)
      const params = new URLSearchParams()
      if (productId) params.set('product', productId)
      if (type) params.set('type', type)
      params.set('page', String(page))
      try {
        const response = await apiFetch(`/stock-movements/?${params.toString()}`)
        if (myRequest !== latest.current) return
        if (response.ok) {
          setData(await response.json())
          setMessage('')
        } else if (response.status === 404 && page > 1) {
          setPage(1)  
        } else if (response.status !== 401) {
          setData(null)
          setMessage('Could not load the history. Please try again.')
        }
      } catch {
        if (myRequest === latest.current) {
          setData(null)
          setMessage('Cannot reach the server. Is Django running?')
        }
      } finally {
        if (myRequest === latest.current) setLoading(false)
      }
    }
    run()
  }, [productId, type, page, version])

  const rows = data?.results ?? []
  const pages = data ? Math.max(1, Math.ceil(data.count / PAGE_SIZE)) : 1

  return (
    <div>
      {loading && <p>Loading...</p>}
      {message && <p style={{ color: 'crimson', fontSize: 16 }}>{message}</p>}
      {!loading && !message && rows.length === 0 && <p style={{ color: '#777' }}>No history lines to show.</p>}

      {rows.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 720 }}>
            <thead>
              <tr style={{ textAlign: 'left', borderBottom: '2px solid #333' }}>
                <th style={cell}>When (Manila)</th>
                <th style={cell}>Product</th>
                <th style={cell}>Type</th>
                <th style={cell}>Change</th>
                <th style={cell}>Balance after</th>
                <th style={cell}>User</th>
                <th style={cell}>Reason</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.id} style={{ borderBottom: '1px solid #ddd' }}>
                  <td style={cell}>{when(m.timestamp)}</td>
                  <td style={cell}>{m.product_name}</td>
                  <td style={cell}>{TYPE_LABEL[m.type] ?? m.type}</td>
                  <td style={{ ...cell, fontWeight: 'bold', color: parseFloat(m.quantity) < 0 ? '#c0392b' : '#1b7f3b' }}>
                    {signed(m.quantity)}
                  </td>
                  <td style={cell}>{num(m.balance_after)}</td>
                  <td style={cell}>{m.user}</td>
                  <td style={cell}>{m.reason || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.count > 0 && (
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 12 }}>
          <button onClick={() => setPage((p) => p - 1)} disabled={!data.previous || loading} style={{ padding: '8px 14px' }}>
            &larr; Newer
          </button>
          <span>Page {page} of {pages} &middot; {data.count} lines</span>
          <button onClick={() => setPage((p) => p + 1)} disabled={!data.next || loading} style={{ padding: '8px 14px' }}>
            Older &rarr;
          </button>
        </div>
      )}
    </div>
  )
}

const cell = { padding: '8px 10px', verticalAlign: 'top' }