import { useEffect, useState } from 'react'
import { apiFetch } from '../api'
import { PESO, flattenErrors, formatTime } from '../utils'

const todayManila = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Manila' })
const addDays = (iso, n) => {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}
const mondayOf = (iso) => addDays(iso, -((new Date(`${iso}T00:00:00Z`).getUTCDay() + 6) % 7))
const m = (v) => (v.startsWith('-') ? `-${PESO}${v.slice(1)}` : `${PESO}${v}`)   // "-5.00" -> "-₱5.00"
const negative = (v) => v.startsWith('-')
const hourLabel = (h) => `${h % 12 || 12} ${h < 12 ? 'AM' : 'PM'}`

function presets() {
  const t = todayManila()
  return [
    ['Today', t, t],
    ['This week', mondayOf(t), t],
    ['This month', `${t.slice(0, 8)}01`, t],
    ['Last 30 days', addDays(t, -29), t],
  ]
}

function useReport(name, params) {
  const [state, setState] = useState({ data: null, error: '', loading: true })
  const key = new URLSearchParams(params).toString()

  useEffect(() => {
    let cancelled = false
    setState((s) => ({ ...s, loading: true }))
    async function run() {
      try {
        const response = await apiFetch(`/owner/reports/${name}/?${key}`)
        if (cancelled) return
        if (response.ok) setState({ data: await response.json(), error: '', loading: false })
        else if (response.status === 400) setState({ data: null, error: flattenErrors(await response.json()).join(' '), loading: false })
        else if (response.status !== 401) setState({ data: null, error: 'Could not load the report. Please try again.', loading: false })
      } catch {
        if (!cancelled) setState({ data: null, error: 'Cannot reach the server. Is Django running?', loading: false })
      }
    }
    run()
    return () => { cancelled = true }
  }, [name, key])

  return state
}

export default function ReportsPage() {
  const first = presets()[2]                                     
  const [tab, setTab] = useState('sales')
  const [range, setRange] = useState({ date_from: first[1], date_to: first[2] })
  const [draft, setDraft] = useState({ date_from: first[1], date_to: first[2] })
  const [rangeError, setRangeError] = useState('')

  function apply(from, to) {
    if (!from || !to) return setRangeError('Choose both dates.')
    if (to < from) return setRangeError('The end date must not be before the start date.')
    setRangeError('')
    setDraft({ date_from: from, date_to: to })
    setRange({ date_from: from, date_to: to })
  }

  const needsRange = tab !== 'slow'

  return (
    <div style={{ maxWidth: 1100 }}>
      <h1>Reports</h1>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
        {[['sales', 'Sales and profit'], ['best', 'Best sellers'], ['hours', 'Busy hours'], ['slow', 'Slow movers']].map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)} disabled={tab === id} style={{ padding: '8px 14px', fontSize: 16 }}>{label}</button>
        ))}
      </div>

      {needsRange && (
        <div style={{ border: '1px solid #ccc', borderRadius: 8, padding: 12, marginBottom: 14, background: '#fafafa' }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
            {presets().map(([label, from, to]) => (
              <button key={label} onClick={() => apply(from, to)} style={{ padding: '6px 12px' }}>{label}</button>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <label>From<br /><input type="date" style={input} value={draft.date_from} onChange={(e) => setDraft({ ...draft, date_from: e.target.value })} /></label>
            <label>To<br /><input type="date" style={input} value={draft.date_to} onChange={(e) => setDraft({ ...draft, date_to: e.target.value })} /></label>
            <button onClick={() => apply(draft.date_from, draft.date_to)} style={{ padding: '8px 16px' }}>Apply</button>
          </div>
          {rangeError && <p style={{ color: 'crimson', margin: '8px 0 0' }}>{rangeError}</p>}
          <small style={{ color: '#777' }}>Manila dates, from midnight at the start of the first day to the end of the last day. Up to 366 days.</small>
        </div>
      )}

      {tab === 'sales' && <SalesTab range={range} />}
      {tab === 'best' && <BestTab range={range} />}
      {tab === 'hours' && <HoursTab range={range} />}
      {tab === 'slow' && <SlowTab />}
    </div>
  )
}

function Status({ state }) {
  if (state.loading && !state.data) return <p>Loading...</p>
  if (state.error) return <p style={{ color: 'crimson', fontSize: 18 }}>{state.error}</p>
  return null
}


function SalesTab({ range }) {
  const [group, setGroup] = useState('day')
  const state = useReport('sales', { ...range, group })
  const { data } = state
  const label = (period) => (group === 'week' ? `Week of ${period}` : group === 'month' ? period.slice(0, 7) : period)

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
        {[['day', 'Daily'], ['week', 'Weekly'], ['month', 'Monthly']].map(([id, text]) => (
          <button key={id} onClick={() => setGroup(id)} disabled={group === id} style={{ padding: '6px 12px' }}>{text}</button>
        ))}
      </div>
      <Status state={state} />
      {data && (
        <>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
            <Stat label="Sales" value={m(data.totals.sales_total)} note={`${data.totals.sales_count} sale(s)`} />
            <Stat label="Profit" value={m(data.totals.profit)} color={negative(data.totals.profit) ? '#c0392b' : undefined}
                  note={`Goods ${m(data.totals.goods_profit)} · Load ${m(data.totals.load_profit)} · GCash fees ${m(data.totals.fees)}`} />
            <Stat label="Bad debt written off" value={m(data.totals.writeoffs)} note="Shown separately, not subtracted" />
          </div>
          <p style={{ color: '#777', margin: '0 0 8px' }}>Expenses are subtracted once the expense log exists. Weeks start on Monday.</p>

          {data.rows.length === 0 ? <p style={{ color: '#777' }}>No sales in this range.</p> : (
            <div style={{ overflowX: 'auto' }}>
              <table style={table}>
                <thead>
                  <tr style={head}>
                    <th style={cell}>Period</th><th style={num}>Sales</th><th style={num}>Sales total</th><th style={num}>On utang</th>
                    <th style={num}>Goods profit</th><th style={num}>Load profit</th><th style={num}>GCash fees</th><th style={num}>Profit</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r) => (
                    <tr key={r.period} style={{ borderBottom: '1px solid #ddd' }}>
                      <td style={cell}><b>{label(r.period)}</b></td><td style={num}>{r.sales_count}</td>
                      <td style={num}>{m(r.sales_total)}</td><td style={num}>{m(r.utang_total)}</td>
                      <td style={num}>{m(r.goods_profit)}</td><td style={num}>{m(r.load_profit)}</td>
                      <td style={num}>{m(r.fees)}</td>
                      <td style={{ ...num, fontWeight: 'bold', color: negative(r.profit) ? '#c0392b' : undefined }}>{m(r.profit)}</td>
                    </tr>
                  ))}
                  <tr style={{ borderTop: '2px solid #333', fontWeight: 'bold' }}>
                    <td style={cell}>TOTAL</td><td style={num}>{data.totals.sales_count}</td>
                    <td style={num}>{m(data.totals.sales_total)}</td><td style={num}>{m(data.totals.utang_total)}</td>
                    <td style={num}>{m(data.totals.goods_profit)}</td><td style={num}>{m(data.totals.load_profit)}</td>
                    <td style={num}>{m(data.totals.fees)}</td><td style={num}>{m(data.totals.profit)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}

          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 20 }}>
            <div style={{ flex: '1 1 420px' }}>
              <h2>By cashier</h2>
              <table style={table}>
                <thead><tr style={head}><th style={cell}>Cashier</th><th style={num}>Sales total</th><th style={num}>Profit</th></tr></thead>
                <tbody>
                  {data.by_cashier.map((r) => (
                    <tr key={r.cashier} style={{ borderBottom: '1px solid #ddd' }}>
                      <td style={cell}><b>{r.cashier}</b></td><td style={num}>{m(r.sales_total)}</td><td style={num}>{m(r.profit)}</td>
                    </tr>
                  ))}
                  {data.by_cashier.length === 0 && <tr><td colSpan={3} style={{ ...cell, color: '#777' }}>Nothing in this range.</td></tr>}
                </tbody>
              </table>
              <small style={{ color: '#777' }}>Profit includes load and GCash fees handled by that cashier.</small>
            </div>
            <div style={{ flex: '1 1 420px' }}>
              <h2>By category (goods)</h2>
              <table style={table}>
                <thead><tr style={head}><th style={cell}>Category</th><th style={num}>Sales total</th><th style={num}>Goods profit</th></tr></thead>
                <tbody>
                  {data.by_category.map((r) => (
                    <tr key={r.category} style={{ borderBottom: '1px solid #ddd' }}>
                      <td style={cell}><b>{r.category}</b></td><td style={num}>{m(r.sales_total)}</td><td style={num}>{m(r.goods_profit)}</td>
                    </tr>
                  ))}
                  {data.by_category.length === 0 && <tr><td colSpan={3} style={{ ...cell, color: '#777' }}>Nothing in this range.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}


function BestTab({ range }) {
  const state = useReport('best-sellers', range)
  const { data } = state
  return (
    <div>
      <Status state={state} />
      {data && (
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          <Ranking title="By quantity sold" rows={data.by_quantity} />
          <Ranking title="By profit" rows={data.by_profit} />
        </div>
      )}
      {data && <p style={{ color: '#777' }}>Quantities are counted in each product's smallest unit (sticks, pieces). The top 20 are shown.</p>}
    </div>
  )
}

function Ranking({ title, rows }) {
  return (
    <div style={{ flex: '1 1 440px' }}>
      <h2>{title}</h2>
      <table style={table}>
        <thead><tr style={head}><th style={cell}>#</th><th style={cell}>Product</th><th style={num}>Quantity</th><th style={num}>Sales</th><th style={num}>Profit</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.product} style={{ borderBottom: '1px solid #ddd' }}>
              <td style={cell}>{i + 1}</td><td style={cell}><b>{r.product}</b></td>
              <td style={num}>{r.quantity} {r.unit}</td><td style={num}>{m(r.sales_total)}</td>
              <td style={{ ...num, color: negative(r.profit) ? '#c0392b' : undefined }}>{m(r.profit)}</td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={5} style={{ ...cell, color: '#777' }}>No sales in this range.</td></tr>}
        </tbody>
      </table>
    </div>
  )
}


function HoursTab({ range }) {
  const state = useReport('hourly', range)
  const { data } = state
  const max = data ? Math.max(1, ...data.hours.map((h) => h.sales_count)) : 1
  return (
    <div>
      <Status state={state} />
      {data && (
        <>
          <p style={{ fontSize: 18 }}>
            {data.busiest_hour === null
              ? 'No sales in this range.'
              : <>Busiest hour: <b>{hourLabel(data.busiest_hour)}</b> (the red bar). Bars show the number of sales in each hour of the day (Manila time), added up over the range.</>}
          </p>
          <div style={{ display: 'flex', gap: 3, height: 230, borderBottom: '2px solid #333' }}>
            {data.hours.map((h) => (
              <div
                key={h.hour}
                title={`${hourLabel(h.hour)}: ${h.sales_count} sale(s), ${PESO}${h.sales_total}`}
                style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', alignItems: 'stretch' }}
              >
                <small style={{ textAlign: 'center', color: '#555' }}>{h.sales_count || ''}</small>
                <div style={{
                  height: `${(h.sales_count / max) * 170}px`, minHeight: h.sales_count ? 3 : 0,
                  background: h.hour === data.busiest_hour ? '#c0392b' : '#4a6fa5',
                }} />
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 3 }}>
            {data.hours.map((h) => (
              <small key={h.hour} style={{ flex: 1, textAlign: 'center', color: '#555' }}>{h.hour}</small>
            ))}
          </div>
          <small style={{ color: '#777' }}>Hour of the day, 0 to 23. Hover a bar for the exact count and amount. Only sales are counted, not load or GCash.</small>
        </>
      )}
    </div>
  )
}


function SlowTab() {
  const [days, setDays] = useState('30')
  const [applied, setApplied] = useState('30')
  const [error, setError] = useState('')
  const state = useReport('slow-movers', { days: applied })
  const { data } = state

  function apply() {
    if (!/^\d{1,3}$/.test(days) || Number(days) < 1 || Number(days) > 365) return setError('Enter a whole number of days from 1 to 365.')
    setError('')
    setApplied(days)
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: 10 }}>
        <label>No sale in the last (days)<br />
          <input style={input} inputMode="numeric" value={days} onChange={(e) => setDays(e.target.value.replace(/\D/g, '').slice(0, 3))} />
        </label>
        <button onClick={apply} style={{ padding: '8px 16px' }}>Apply</button>
      </div>
      {error && <p style={{ color: 'crimson' }}>{error}</p>}
      <Status state={state} />
      {data && (
        <>
          <p style={{ fontSize: 18 }}>
            <b>{data.count}</b> item(s) with no sale in {data.days} days are holding <b>{PESO}{data.tied_up}</b> of stock (at cost).
          </p>
          <div style={{ overflowX: 'auto' }}>
            <table style={table}>
              <thead><tr style={head}><th style={cell}>Product</th><th style={num}>In stock</th><th style={num}>Value at cost</th><th style={cell}>Last sold</th></tr></thead>
              <tbody>
                {data.items.map((r) => (
                  <tr key={r.id} style={{ borderBottom: '1px solid #ddd' }}>
                    <td style={cell}><b>{r.name}</b></td><td style={num}>{r.stock} {r.unit}</td><td style={num}>{PESO}{r.value}</td>
                    <td style={cell}>{r.last_sold ? `${r.days_since} day(s) ago (${formatTime(r.last_sold)})` : 'Never sold'}</td>
                  </tr>
                ))}
                {data.items.length === 0 && <tr><td colSpan={4} style={{ ...cell, color: '#777' }}>Nothing is slow. Every item with stock sold recently.</td></tr>}
              </tbody>
            </table>
          </div>
          <small style={{ color: '#777' }}>Items added less than {data.days} days ago, items with no stock, inactive items and items with no selling unit are not listed.</small>
        </>
      )}
    </div>
  )
}

function Stat({ label, value, note, color }) {
  return (
    <div style={{ border: '1px solid #ccc', borderRadius: 8, padding: '10px 16px', minWidth: 200, flex: '1 1 220px' }}>
      <div style={{ color: '#555' }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 'bold', color }}>{value}</div>
      {note && <small style={{ color: '#555' }}>{note}</small>}
    </div>
  )
}

const table = { borderCollapse: 'collapse', width: '100%', minWidth: 360 }
const head = { textAlign: 'left', borderBottom: '2px solid #333' }
const cell = { padding: '8px 10px', verticalAlign: 'top' }
const num = { ...cell, textAlign: 'right' }
const input = { padding: 8, fontSize: 16 }