import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api'
import CashCountForm from '../components/CashCountForm'
import { PESO, flattenErrors, formatTime, signedPeso, toCents } from '../utils'

const varianceColor = (v) => (parseFloat(v) < 0 ? '#c0392b' : parseFloat(v) > 0 ? '#b86e00' : '#1b7f3b')

export default function ShiftsPage() {
  const [shifts, setShifts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [closing, setClosing] = useState(false)
  const [reopenId, setReopenId] = useState(null)

  const load = useCallback(async () => {
    try {
      const response = await apiFetch('/shifts/')
      if (response.ok) {
        setShifts(await response.json())
        setError('')
      } else if (response.status !== 401) {
        setError('Could not load shifts. Please try again.')
      }
    } catch {
      setError('Cannot reach the server. Is Django running?')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function send(path, body) {
    try {
      const response = await apiFetch(path, { method: 'POST', body: JSON.stringify(body) })
      if (response.ok) {
        await load()   // always show what the server really saved
        return ''
      }
      if (response.status === 400) return flattenErrors(await response.json()).join(' ')
      if (response.status === 401) return 'Your session ended. Please log in again.'
      if (response.status === 404) return 'That shift was not found.'
      return 'Something went wrong. Please try again.'
    } catch {
      return 'Cannot reach the server. Is Django running?'
    }
  }

  const open = shifts.find((s) => s.status === 'open')
  const latestId = shifts[0]?.id

  async function closeOnBehalf(payload) {
    const message = await send(`/shifts/${open.id}/close/`, payload)
    if (!message) {
      setClosing(false)
      setNotice(`Shift #${open.id} (${open.cashier}) was closed on their behalf.`)
    }
    return message
  }

  async function reopen(shift, reason) {
    const message = await send(`/shifts/${shift.id}/reopen/`, { reason })
    if (!message) {
      setReopenId(null)
      setNotice(`Shift #${shift.id} is open again. The old count is saved in the reopen log.`)
    }
    return message
  }

  return (
    <div style={{ maxWidth: 1100 }}>
      <h1>Shifts</h1>
      {notice && <p style={{ background: '#f3fbf5', border: '1px solid #1b7f3b', padding: 10, borderRadius: 6 }}>{notice}</p>}
      {loading && <p>Loading...</p>}
      {error && <p style={{ color: 'crimson', fontSize: 18 }}>{error}</p>}

      {!loading && !error && (
        <div style={{ border: '1px solid #ccc', borderRadius: 8, padding: 14, marginBottom: 20 }}>
          <b>Open shift</b>
          {!open && <p style={{ margin: '6px 0 0', color: '#555' }}>No shift is open right now.</p>}
          {open && (
            <>
              <p style={{ margin: '6px 0' }}>
                <b>{open.cashier}</b> since {formatTime(open.start_time)}, opening cash {PESO}{open.opening_cash}.
              </p>
              {!closing ? (
                <button onClick={() => { setClosing(true); setNotice('') }} style={{ padding: '8px 14px' }}>
                  Close this shift on {open.cashier}'s behalf
                </button>
              ) : (
                <div style={{ maxWidth: 520, background: '#fafafa', border: '1px solid #999', borderRadius: 8, padding: 14, marginTop: 8 }}>
                  <p style={{ marginTop: 0, color: '#555' }}>
                    You count the drawer yourself. Your name and the reason are saved on the shift
                    and shown in its report.
                  </p>
                  <CashCountForm submitLabel="Submit count and close shift" needReason onSubmit={closeOnBehalf} />
                  <button onClick={() => setClosing(false)} style={{ marginTop: 8, padding: '6px 12px' }}>Cancel</button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {shifts.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 900 }}>
            <thead>
              <tr style={{ textAlign: 'left', borderBottom: '2px solid #333' }}>
                <th style={cell}>#</th>
                <th style={cell}>Cashier</th>
                <th style={cell}>Started</th>
                <th style={cell}>Ended</th>
                <th style={cell}>Opening</th>
                <th style={cell}>Expected</th>
                <th style={cell}>Counted</th>
                <th style={cell}>Variance</th>
                <th style={cell}>Notes</th>
                <th style={cell}></th>
              </tr>
            </thead>
            <tbody>
              {shifts.map((s) => (
                <ShiftRow
                  key={s.id}
                  shift={s}
                  canReopen={s.status === 'closed' && s.id === latestId}
                  reopening={reopenId === s.id}
                  onStartReopen={() => { setReopenId(s.id); setNotice('') }}
                  onCancelReopen={() => setReopenId(null)}
                  onReopen={(reason) => reopen(s, reason)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!loading && !error && shifts.length === 0 && <p style={{ color: '#777' }}>No shifts yet.</p>}
    </div>
  )
}

function ShiftRow({ shift: s, canReopen, reopening, onStartReopen, onCancelReopen, onReopen }) {
  const isOpen = s.status === 'open'
  const notes = []
  if (s.opening_difference !== null && parseFloat(s.opening_difference) !== 0) {
    notes.push(
      `Opening cash was ${signedPeso(toCents(s.opening_difference))} compared with the last count (${PESO}${s.previous_closing_cash}).`
    )
  }
  if (s.closed_on_behalf) notes.push(`Closed by ${s.closed_by} on the cashier's behalf: "${s.close_reason}"`)
  if (s.reopen_count > 0) notes.push(`Reopened ${s.reopen_count} time(s).`)

  return (
    <>
      <tr style={{ borderBottom: '1px solid #ddd' }}>
        <td style={cell}>{s.id}</td>
        <td style={cell}><b>{s.cashier}</b></td>
        <td style={cell}>{formatTime(s.start_time)}</td>
        <td style={cell}>{isOpen ? <b style={{ color: '#1b7f3b' }}>Open</b> : formatTime(s.end_time)}</td>
        <td style={cell}>{PESO}{s.opening_cash}</td>
        <td style={cell}>{s.expected_cash ? `${PESO}${s.expected_cash}` : '-'}</td>
        <td style={cell}>{s.counted_cash ? `${PESO}${s.counted_cash}` : '-'}</td>
        <td style={{ ...cell, fontWeight: 'bold', color: s.variance ? varianceColor(s.variance) : undefined }}>
          {s.variance !== null ? signedPeso(toCents(s.variance)) : '-'}
        </td>
        <td style={{ ...cell, fontSize: 13, maxWidth: 300 }}>
          {notes.map((n) => <div key={n}>{n}</div>)}
        </td>
        <td style={{ ...cell, whiteSpace: 'nowrap' }}>
          {canReopen && !reopening && <button onClick={onStartReopen} style={{ padding: '6px 10px' }}>Reopen</button>}
        </td>
      </tr>
      {reopening && (
        <tr>
          <td colSpan={10} style={{ padding: 10, background: '#fafafa' }}>
            <ReopenForm shift={s} onSave={onReopen} onCancel={onCancelReopen} />
          </td>
        </tr>
      )}
    </>
  )
}

function ReopenForm({ shift, onSave, onCancel }) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)

  async function handleSubmit(event) {
    event.preventDefault()
    if (busyRef.current) return
    if (!reason.trim()) return setError('Enter the reason. It is required and logged.')
    const ok = window.confirm(
      `Reopen shift #${shift.id}?\n\nIts count (${PESO}${shift.counted_cash}) is cleared and saved in the reopen log. ` +
      `${shift.cashier} can sell again and must close it again.`
    )
    if (!ok) return
    busyRef.current = true
    setBusy(true)
    setError('')
    const message = await onSave(reason.trim())   
    busyRef.current = false
    if (message) {
      setError(message)
      setBusy(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
      <input
        style={{ padding: 8, fontSize: 16, flex: 1, minWidth: 260 }}
        maxLength={200}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Reason for reopening (required)"
        autoFocus
      />
      <button type="submit" disabled={busy} style={{ padding: '8px 14px' }}>{busy ? 'Saving...' : 'Reopen shift'}</button>
      <button type="button" onClick={onCancel} disabled={busy} style={{ padding: '8px 14px' }}>Cancel</button>
      {error && <span style={{ color: 'crimson', width: '100%' }}>{error}</span>}
    </form>
  )
}

const cell = { padding: '8px 10px', verticalAlign: 'top' }