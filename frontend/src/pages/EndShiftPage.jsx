import { useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../api'
import CashCountForm from '../components/CashCountForm'
import { useCurrentShift } from '../useCurrentShift'
import { PESO, flattenErrors, formatTime, signedPeso, toCents } from '../utils'

export default function EndShiftPage() {
  const { loading, error, shift, isMine } = useCurrentShift()
  const [result, setResult] = useState(null)   
  
  async function endShift(payload) {
    try {
      const response = await apiFetch('/shifts/end/', { method: 'POST', body: JSON.stringify(payload) })
      if (response.ok) {
        setResult(await response.json())
        return ''
      }
      if (response.status === 400) return flattenErrors(await response.json()).join(' ')
      if (response.status === 401) return 'Your session ended. Please log in again.'
      return 'Something went wrong. Check your shift status before trying again.'
    } catch {
      return 'Connection lost. Your shift may have been closed. Go back and check before trying again.'
    }
  }

  return (
    <div style={{ maxWidth: 520, margin: '0 auto', padding: 16, fontFamily: 'sans-serif' }}>
      <p><Link to="/">&larr; Back</Link></p>
      <h1>End Shift</h1>

      {result && <Result result={result} />}

      {!result && loading && <p>Loading...</p>}
      {!result && error && <p style={{ color: 'crimson', fontSize: 18 }}>{error}</p>}
      {!result && !loading && !error && !isMine && (
        <p style={{ background: '#fdecea', padding: 14, borderRadius: 8 }}>
          {shift ? `${shift.cashier} has the shift open. Only they (or the owner) can end it.` : 'You have no open shift to end.'}
        </p>
      )}
      {!result && !loading && !error && isMine && (
        <>
          <p style={{ color: '#555' }}>
            Shift started {formatTime(shift.start_time)}. Take all the money out of the drawer and count it.
            Type <b>exactly what you counted</b>. The system compares it with what should be there
            <b> after</b> you submit.
          </p>
          <CashCountForm submitLabel="Submit count and end shift" onSubmit={endShift} />
        </>
      )}
    </div>
  )
}

function Result({ result }) {
  const { shift, sales_count: salesCount, cash_sales: cashSales } = result
  const varianceCents = toCents(shift.variance)
  const color = varianceCents < 0 ? '#c0392b' : varianceCents > 0 ? '#b86e00' : '#1b7f3b'
  const label = varianceCents < 0 ? 'SHORT' : varianceCents > 0 ? 'OVER' : 'EXACT'

  return (
    <div style={{ border: '2px solid #1b7f3b', borderRadius: 8, padding: 16, background: '#f3fbf5' }}>
      <b style={{ color: '#1b7f3b', fontSize: 20 }}>Shift ended</b>
      <p style={{ margin: '4px 0' }}>{formatTime(shift.start_time)} to {formatTime(shift.end_time)}</p>
      <table style={{ width: '100%', margin: '8px 0' }}>
        <tbody>
          <Row label="Opening cash" value={`${PESO}${shift.opening_cash}`} />
          <Row label={`Cash sales (${salesCount} sales)`} value={`${PESO}${cashSales}`} />
          <Row label="Expected cash" value={`${PESO}${shift.expected_cash}`} />
          <Row label="Counted cash" value={`${PESO}${shift.counted_cash}`} />
        </tbody>
      </table>
      <div style={{ fontSize: 26, fontWeight: 'bold', color }}>
        {label} {varianceCents !== 0 && signedPeso(varianceCents)}
      </div>
      <p style={{ color: '#555' }}>
        This shift is now locked. You can log out. If something looks wrong, tell the owner.
      </p>
      <Link to="/"><b>Back to home</b></Link>
    </div>
  )
}

function Row({ label, value }) {
  return (
    <tr>
      <td style={{ padding: '3px 0' }}>{label}</td>
      <td style={{ textAlign: 'right' }}><b>{value}</b></td>
    </tr>
  )
}