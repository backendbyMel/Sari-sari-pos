import { useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../api'
import CashCountForm from '../components/CashCountForm'
import { useCurrentShift } from '../useCurrentShift'
import { PESO, flattenErrors, formatTime, signedPeso, toCents } from '../utils'
import PdfPreview from '../components/PdfPreview'

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
  const [viewing, setViewing] = useState(false)
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
          <Row label="Sold on utang (no cash)" value={`${PESO}${result.utang_given}`} />
          <Row label="Utang payments received" value={`${PESO}${result.utang_collected}`} />
          <Row label={`Mobile load sales (${result.load_count} loads)`} value={`${PESO}${result.load_sales}`} />
          <Row label="GCash cash in received" value={`${PESO}${result.ewallet_in}`} />
          <Row label="GCash cash out paid" value={`${PESO}${result.ewallet_out}`} />
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

      {result.wallet_checks.length > 0 && (
        <div style={{ margin: '10px 0' }}>
          <b>Wallet check</b>
          <table style={{ width: '100%', marginTop: 4 }}>
            <thead>
              <tr style={{ textAlign: 'left', fontSize: 13 }}>
                <th>Wallet</th><th>Expected</th><th>You typed</th><th>Difference</th>
              </tr>
            </thead>
            <tbody>
              {result.wallet_checks.map((w) => {
                const gap = toCents(w.gap)
                return (
                  <tr key={w.wallet}>
                    <td>{w.wallet}</td>
                    <td>{PESO}{w.expected}</td>
                    <td>{PESO}{w.actual}</td>
                    <td style={{ fontWeight: 'bold', color: gap < 0 ? '#c0392b' : gap > 0 ? '#b86e00' : '#1b7f3b' }}>
                      {gap === 0 ? 'EXACT' : signedPeso(gap)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {result.report ? (
        <p>
          <button onClick={() => setViewing(true)} style={{ padding: '10px 16px', fontSize: 16 }}>
            View my shift report (PDF)
          </button>
        </p>
      ) : (
        <p style={{ color: '#b86e00' }}>
          The shift is closed, but its PDF report could not be made. Please tell the owner.
        </p>
      )}
      {viewing && result.report && (
        <PdfPreview
          shiftId={shift.id}
          copy="cashier"
          filename={`${result.report.report_no}-cashier.pdf`}
          onClose={() => setViewing(false)}
        />
      )}

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