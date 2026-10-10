import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api'
import PdfPreview from '../components/PdfPreview'
import { PESO, flattenErrors, formatTime, signedPeso, toCents } from '../utils'

const EMPTY = { date_from: '', date_to: '', cashier: '', variance: false }
const color = (v) => (parseFloat(v) < 0 ? '#c0392b' : parseFloat(v) > 0 ? '#b86e00' : '#1b7f3b')

export default function ShiftReportsPage() {
  const [form, setForm] = useState(EMPTY)         // what is typed
  const [applied, setApplied] = useState(EMPTY)   // what the list was loaded with
  const [rows, setRows] = useState([])
  const [cashiers, setCashiers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [preview, setPreview] = useState(null)    // { shiftId, copy, filename }
  const latest = useRef(0)                        // ignores stale answers

  useEffect(() => {
    async function loadCashiers() {
      try {
        const response = await apiFetch('/users/')
        if (response.ok) setCashiers(await response.json())
      } catch {
        // the filter dropdown just stays empty
      }
    }
    loadCashiers()
  }, [])

  useEffect(() => {
    const myRequest = ++latest.current
    async function run() {
      setLoading(true)
      const params = new URLSearchParams()
      if (applied.date_from) params.set('date_from', applied.date_from)
      if (applied.date_to) params.set('date_to', applied.date_to)
      if (applied.cashier) params.set('cashier', applied.cashier)
      if (applied.variance) params.set('variance', '1')
      try {
        const response = await apiFetch(`/shifts/?${params.toString()}`)
        if (myRequest !== latest.current) return
        if (response.ok) {
          setRows(await response.json())
          setError('')
        } else if (response.status === 400) {
          setRows([])
          setError(flattenErrors(await response.json()).join(' '))
        } else if (response.status !== 401) {
          setRows([])
          setError('Could not load the shifts. Please try again.')
        }
      } catch {
        if (myRequest === latest.current) {
          setRows([])
          setError('Cannot reach the server. Is Django running?')
        }
      } finally {
        if (myRequest === latest.current) setLoading(false)
      }
    }
    run()
  }, [applied])

  function handleFilter(event) {
    event.preventDefault()
    setNotice('')
    setApplied({ ...form })
  }

  function clearFilters() {
    setForm(EMPTY)
    setApplied(EMPTY)
  }

  async function generate(shift) {
    setNotice('')
    try {
      const response = await apiFetch(`/shifts/${shift.id}/report/generate/`, { method: 'POST' })
      if (response.ok) {
        setNotice(`Report created for shift #${shift.id}.`)
        setApplied({ ...applied })   // a new object makes the list load again
      } else if (response.status !== 401) {
        setError('Could not create the report. Paste the server error to your developer.')
      }
    } catch {
      setError('Cannot reach the server. Is Django running?')
    }
  }

  return (
    <div style={{ maxWidth: 1100 }}>
      <h1>Shift Reports</h1>

      <form onSubmit={handleFilter} style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'flex-end', margin: '12px 0' }}>
        <label>From<br />
          <input type="date" style={input} value={form.date_from} onChange={(e) => setForm({ ...form, date_from: e.target.value })} />
        </label>
        <label>To<br />
          <input type="date" style={input} value={form.date_to} onChange={(e) => setForm({ ...form, date_to: e.target.value })} />
        </label>
        <label>Cashier<br />
          <select style={input} value={form.cashier} onChange={(e) => setForm({ ...form, cashier: e.target.value })}>
            <option value="">All cashiers</option>
            {cashiers.map((c) => <option key={c.id} value={c.id}>{c.username}</option>)}
          </select>
        </label>
        <label style={{ paddingBottom: 8 }}>
          <input type="checkbox" checked={form.variance} onChange={(e) => setForm({ ...form, variance: e.target.checked })} />{' '}
          Only with a variance (cash or wallet)
        </label>
        <button type="submit" style={{ padding: '8px 16px' }}>Apply</button>
        <button type="button" onClick={clearFilters} style={{ padding: '8px 16px' }}>Clear</button>
      </form>

      {notice && <p style={{ background: '#f3fbf5', border: '1px solid #1b7f3b', padding: 10, borderRadius: 6 }}>{notice}</p>}
      {loading && <p>Loading...</p>}
      {error && <p style={{ color: 'crimson', fontSize: 18 }}>{error}</p>}
      {!loading && !error && rows.length === 0 && <p style={{ color: '#777' }}>No shifts match.</p>}

      {rows.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 800 }}>
            <thead>
              <tr style={{ textAlign: 'left', borderBottom: '2px solid #333' }}>
                <th style={cell}>Report</th>
                <th style={cell}>Cashier</th>
                <th style={cell}>Shift</th>
                <th style={cell}>Variance</th>
                <th style={cell}>Notes</th>
                <th style={cell}></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id} style={{ borderBottom: '1px solid #ddd' }}>
                  <td style={cell}>{s.report ? <b>{s.report.report_no}</b> : <span style={{ color: '#777' }}>none</span>}</td>
                  <td style={cell}>{s.cashier}</td>
                  <td style={cell}>
                    #{s.id}<br />
                    <small>{formatTime(s.start_time)}{s.end_time ? ` to ${formatTime(s.end_time)}` : ''}</small>
                  </td>
                  <td style={{ ...cell, fontWeight: 'bold', color: s.variance !== null ? color(s.variance) : undefined }}>
                    {s.status === 'open' ? <span style={{ color: '#1b7f3b' }}>Open</span> : signedPeso(toCents(s.variance))}
                  </td>
                  <td style={{ ...cell, fontSize: 13 }}>
                    {s.closed_on_behalf && <div>Closed by {s.closed_by} on behalf: "{s.close_reason}"</div>}
                    {s.reopen_count > 0 && <div>Reopened {s.reopen_count} time(s)</div>}
                    {s.payouts_count > 0 && <div>Pay-outs {PESO}{s.payouts_total}</div>}
                    {(s.wallet_checks ?? []).map((w) => (
                      <div key={w.wallet}>
                        {parseFloat(w.start_gap) !== 0 && <div>{w.wallet}: start {signedPeso(toCents(w.start_gap))} vs system</div>}
                        {w.gap !== null && parseFloat(w.gap) !== 0 && <div>{w.wallet}: end {signedPeso(toCents(w.gap))}</div>}
                      </div>
                    ))}

                  </td>
                  <td style={{ ...cell, whiteSpace: 'nowrap' }}>
                    {s.report && (
                      <>
                        <button style={btn} onClick={() => setPreview({ shiftId: s.id, copy: 'owner', filename: `${s.report.report_no}-owner.pdf` })}>
                          Owner copy
                        </button>{' '}
                        <button style={btn} onClick={() => setPreview({ shiftId: s.id, copy: 'cashier', filename: `${s.report.report_no}-cashier.pdf` })}>
                          Cashier copy
                        </button>
                      </>
                    )}
                    {!s.report && s.status === 'closed' && (
                      <button style={btn} onClick={() => generate(s)}>Create report</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p style={{ color: '#777' }}>Showing up to the latest 100 matching shifts.</p>

      {preview && (
        <PdfPreview
          key={`${preview.shiftId}-${preview.copy}`}
          shiftId={preview.shiftId}
          copy={preview.copy}
          filename={preview.filename}
          onClose={() => setPreview(null)}
        />
      )}
    </div>
  )
}

const cell = { padding: '8px 10px', verticalAlign: 'top' }
const input = { padding: 8, fontSize: 16 }
const btn = { padding: '6px 10px' }