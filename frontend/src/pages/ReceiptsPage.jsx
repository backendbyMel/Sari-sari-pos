import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../api'
import ReceiptView from '../components/ReceiptView'
import { PESO } from '../utils'

export default function ReceiptsPage() {
  const [search, setSearch] = useState('')
  const [sales, setSales] = useState([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [open, setOpen] = useState(null)          
  const [reprinting, setReprinting] = useState(false)
  const [modalError, setModalError] = useState('')

  const latest = useRef(0)                       
  const reprintingRef = useRef(false)             
  async function loadList(term) {
    const myRequest = ++latest.current
    setLoading(true)
    setMessage('')
    try {
      const response = await apiFetch(`/sales/recent/?receipt=${encodeURIComponent(term)}`)
      if (myRequest !== latest.current) return
      if (response.ok) {
        const data = await response.json()
        setSales(data)
        if (data.length === 0) setMessage('No sales found.')
      } else if (response.status !== 401) {
        setSales([])
        setMessage('Something went wrong. Please try again.')
      }
    } catch {
      if (myRequest === latest.current) {
        setSales([])
        setMessage('Cannot reach the server. Is Django running?')
      }
    } finally {
      if (myRequest === latest.current) setLoading(false)
    }
  }

  useEffect(() => { loadList('') }, [])

  function handleSearch(event) {
    event.preventDefault()
    loadList(search.trim())
  }

  async function openReceipt(receiptNo) {
    setMessage('')
    setModalError('')
    try {
      const response = await apiFetch(`/receipts/${encodeURIComponent(receiptNo)}/`)
      if (response.ok) {
        setOpen({ receipt: await response.json(), printed: false })
      } else if (response.status === 404) {
        setMessage('Receipt not found.')
      } else if (response.status !== 401) {
        setMessage('Something went wrong. Please try again.')
      }
    } catch {
      setMessage('Cannot reach the server. Is Django running?')
    }
  }

  async function reprint() {
    if (reprintingRef.current || !open) return
    reprintingRef.current = true
    setReprinting(true)
    setModalError('')
    try {
      const response = await apiFetch(
        `/receipts/${encodeURIComponent(open.receipt.receipt_no)}/reprint/`,
        { method: 'POST' }
      )
      if (response.ok) {
        setOpen({ receipt: await response.json(), printed: false })
      } else if (response.status !== 401) {
        setModalError('Reprint failed. Nothing was printed. Please try again.')
      }
    } catch {
      setModalError('Cannot reach the server. Nothing was printed.')
    } finally {
      reprintingRef.current = false
      setReprinting(false)
    }
  }

  function printCopy() {
    window.print()
    setOpen((current) => ({ ...current, printed: true }))
  }

  return (
    <div style={{ maxWidth: 760, margin: '0 auto', padding: 16, fontFamily: 'sans-serif' }}>
      <p><Link to="/">&larr; Back</Link></p>
      <h1>Receipts</h1>

      <form onSubmit={handleSearch} style={{ display: 'flex', gap: 8 }}>
        <input
          style={{ flex: 1, padding: 12, fontSize: 18 }}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Receipt number, e.g. 000123"
          autoComplete="off"
          autoFocus
        />
        <button type="submit" style={{ padding: '0 18px', fontSize: 16 }}>Search</button>
      </form>

      <p style={{ color: '#777' }}>
        Showing the latest 30 sales{search.trim() && ' that match your search'}.
      </p>
      {loading && <p>Loading...</p>}
      {message && <p style={{ color: 'crimson', fontSize: 18 }}>{message}</p>}

      {sales.map((sale) => (
        <div
          key={sale.receipt_no}
          style={{
            display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
            border: '1px solid #ccc', borderRadius: 8, padding: 10, marginBottom: 8,
          }}
        >
          <div style={{ flex: 1, minWidth: 180 }}>
            <b>{sale.receipt_no}</b>
            {sale.status === 'voided' && (
              <span style={{ color: '#c0392b', fontWeight: 'bold' }}> VOIDED</span>
            )}
            <div style={{ color: '#555', fontSize: 14 }}>{sale.date_time} &middot; {sale.cashier}</div>
          </div>
          <b style={{ fontSize: 18 }}>{PESO}{sale.total}</b>
          <button style={{ padding: '8px 14px' }} onClick={() => openReceipt(sale.receipt_no)}>
            Open
          </button>
        </div>
      ))}

      {open && (
        <div
          className="sale-overlay"
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', overflow: 'auto',
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
          }}
        >
          <div className="sale-panel" style={{ background: '#fff', borderRadius: 8, padding: 16, maxHeight: '95vh', overflow: 'auto' }}>
            {open.receipt.is_copy ? (
              <p style={{ margin: '0 0 8px', maxWidth: 300, color: '#1b7f3b' }}>
                Reprint recorded under your name.
              </p>
            ) : (
              <p style={{ margin: '0 0 8px', maxWidth: 300, color: '#555' }}>
                Original receipt, <b>view only</b>. To print it, reprint it as a COPY.
                Every reprint is logged.
              </p>
            )}

            
            {open.receipt.is_copy ? (
              <ReceiptView receipt={open.receipt} />
            ) : (
              <div className="no-print"><ReceiptView receipt={open.receipt} /></div>
            )}

            {modalError && <p style={{ color: 'crimson', maxWidth: 300 }}>{modalError}</p>}

            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              {!open.receipt.is_copy && (
                <button onClick={reprint} disabled={reprinting} style={{ flex: 2, padding: 12 }}>
                  {reprinting ? 'Reprinting...' : 'Reprint as COPY'}
                </button>
              )}
              {open.receipt.is_copy && !open.printed && (
                <button onClick={printCopy} style={{ flex: 2, padding: 12 }}>Print</button>
              )}
              {open.receipt.is_copy && open.printed && (
                <button onClick={reprint} disabled={reprinting} style={{ flex: 2, padding: 12 }}>
                  {reprinting ? 'Reprinting...' : 'Reprint again (logged)'}
                </button>
              )}
              <button onClick={() => setOpen(null)} style={{ flex: 1, padding: 12 }}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}