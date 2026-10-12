import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../api'
import { PESO, formatTime, signedPeso, toCents } from '../utils'

const REFRESH_MS = 60 * 1000

export default function DashboardPage() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [updated, setUpdated] = useState(null)
  const latest = useRef(0)   // ignores stale answers

  const load = useCallback(async () => {
    const mine = ++latest.current
    try {
      const response = await apiFetch('/owner/dashboard/')
      if (mine !== latest.current) return
      if (response.ok) {
        setData(await response.json())
        setUpdated(new Date())
        setError('')
      } else if (response.status !== 401) {
        setError('Could not load the dashboard. Please try again.')
      }
    } catch {
      if (mine === latest.current) setError('Cannot reach the server. Is Django running?')
    }
  }, [])

  useEffect(() => {
    load()
    const timer = setInterval(load, REFRESH_MS)   
    return () => clearInterval(timer)
  }, [load])

  if (!data) return error ? <p style={{ color: 'crimson', fontSize: 18 }}>{error}</p> : <p>Loading...</p>

  const t = data.today
  const varianceColor = (v) => (toCents(v) < 0 ? '#c0392b' : toCents(v) > 0 ? '#b86e00' : '#1b7f3b')

  return (
    <div style={{ maxWidth: 1100 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <h1 style={{ margin: 0 }}>Dashboard <small style={{ color: '#777', fontSize: 16 }}>{data.date}</small></h1>
        <span style={{ color: '#777' }}>
          {updated && `Updated ${updated.toLocaleTimeString('en-PH', { timeZone: 'Asia/Manila' })}`}{' '}
          <button onClick={load} style={{ padding: '6px 12px' }}>Refresh</button>
        </span>
      </div>
      {error && <p style={{ color: 'crimson' }}>{error} (showing the last numbers we had)</p>}

      <div style={grid}>
        <Card title="Sales today">
          <Big>{PESO}{t.sales_total}</Big>
          <Small>{t.sales_count} sale(s), of which {PESO}{t.utang_sales_total} on utang</Small>
          <Small>Mobile load {PESO}{t.load_sales} &middot; GCash transactions {t.ewallet_count}</Small>
        </Card>

        <Card title="Profit today">
          <Big>{PESO}{t.profit}</Big>
          <Small>Goods {PESO}{t.goods_profit}</Small>
          <Small>Mobile load {PESO}{t.load_profit}</Small>
          <Small>GCash fees {PESO}{t.ewallet_fees}</Small>
          <Small>Bad debt written off today: {PESO}{t.writeoffs} (not subtracted)</Small>
          <Small>Expenses are subtracted once the expense log exists.</Small>
        </Card>

        <Card title="Shift">
          {data.open_shift ? (
            <p style={{ margin: '4px 0' }}>
              <b>{data.open_shift.cashier}</b> has the shift open since {formatTime(data.open_shift.start_time)}
              <br /><Small>Opening cash {PESO}{data.open_shift.opening_cash}</Small>
            </p>
          ) : <p style={{ margin: '4px 0', color: '#777' }}>No shift is open.</p>}
          {data.last_shift ? (
            <p style={{ margin: '8px 0 0' }}>
              Last shift: <b>{data.last_shift.cashier}</b>, {formatTime(data.last_shift.end_time)}<br />
              <b style={{ color: varianceColor(data.last_shift.variance), fontSize: 20 }}>
                {toCents(data.last_shift.variance) === 0 ? 'Cash EXACT' : `Cash ${signedPeso(toCents(data.last_shift.variance))}`}
              </b>
              {data.last_shift.wallet_flags > 0 && <b style={{ color: '#b86e00' }}> &middot; {data.last_shift.wallet_flags} wallet difference(s)</b>}
              {data.last_shift.closed_on_behalf && <Small>Closed by the owner on the cashier's behalf</Small>}
            </p>
          ) : <Small>No finished shift yet.</Small>}
          <p style={{ margin: '8px 0 0' }}><Link to="/owner/shifts">Shifts</Link> &middot; <Link to="/owner/shift-reports">Reports</Link></p>
        </Card>

        <Card title="Wallets">
          {data.wallets.length === 0 && <Small>No wallets yet.</Small>}
          {data.wallets.map((w) => (
            <p key={w.id} style={{ margin: '4px 0', color: w.is_low ? '#c0392b' : undefined }}>
              {w.provider}: <b>{PESO}{w.balance}</b> {w.is_low && <b>LOW (alert at {PESO}{w.low_level})</b>}
            </p>
          ))}
          <Small>What the system expects. Compare with the apps.</Small>
          <p style={{ margin: '4px 0 0' }}><Link to="/owner/wallet">Load wallet</Link> &middot; <Link to="/owner/gcash-wallet">GCash wallet</Link></p>
        </Card>

        <Card title="Utang">
          <Big>{PESO}{data.utang.total_unpaid}</Big>
          <Small>{data.utang.owing_count} customer(s) owing</Small>
          <p style={{ margin: '4px 0', color: data.utang.overdue_count > 0 ? '#c0392b' : '#1b7f3b' }}>
            <b>{data.utang.overdue_count}</b> overdue (over {data.utang.overdue_days} days)
          </p>
          <Link to="/owner/customers">Open Utang</Link>
        </Card>

        <Card title="Needs restocking">
          {data.low_stock.recount_count > 0 && (
            <p style={{ margin: '4px 0', color: '#b86e00' }}><b>{data.low_stock.recount_count}</b> item(s) need a recount</p>
          )}
          {data.low_stock.count === 0 && <Small>Nothing is low.</Small>}
          {data.low_stock.items.map((p) => (
            <p key={p.id} style={{ margin: '4px 0', color: p.status === 'out' ? '#c0392b' : '#b86e00' }}>
              <b>{p.name}</b>: {p.stock} {p.unit} <small>({p.status === 'out' ? 'OUT' : `low, level ${p.low_level}`})</small>
            </p>
          ))}
          {data.low_stock.count > data.low_stock.items.length && (
            <Small>and {data.low_stock.count - data.low_stock.items.length} more</Small>
          )}
          {/* <Link to="/owner/restock">Restock</Link> */}
          <Link to="/owner/restock">Restock</Link> &middot; <Link to="/owner/shopping-list">Shopping list</Link>
        </Card>

        <Card title="Best sellers today">
          {data.best_sellers.length === 0 && <Small>No sales yet today.</Small>}
          {data.best_sellers.map((b, i) => (
            <p key={b.product} style={{ margin: '4px 0' }}>
              {i + 1}. <b>{b.product}</b>: {PESO}{b.amount} <small style={{ color: '#777' }}>({b.quantity} {b.unit})</small>
            </p>
          ))}
        </Card>

        <Card title="Coming later">
          <Small>Items expiring soon, and recent voids, arrive in Phase 5 with expiry tracking and voids.</Small>
        </Card>
      </div>
    </div>
  )
}

function Card({ title, children }) {
  return (
    <div style={{ border: '1px solid #ccc', borderRadius: 8, padding: 14, background: '#fff' }}>
      <div style={{ color: '#555', fontWeight: 'bold', marginBottom: 6 }}>{title}</div>
      {children}
    </div>
  )
}
const Big = ({ children }) => <div style={{ fontSize: 32, fontWeight: 'bold' }}>{children}</div>
const Small = ({ children }) => <div style={{ color: '#555', fontSize: 14, margin: '2px 0' }}>{children}</div>
const grid = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 14, marginTop: 14 }