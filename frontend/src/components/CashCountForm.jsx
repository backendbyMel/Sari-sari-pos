import { useRef, useState } from 'react'
import { PESO, peso, toCents } from '../utils'

const BILLS = ['1000', '500', '200', '100', '50', '20']
const MONEY_OK = /^\d+(\.\d{1,2})?$/  

export default function CashCountForm({ submitLabel, needReason = false, onSubmit }) {
  const [mode, setMode] = useState('breakdown')   
  const [counts, setCounts] = useState({})        
  const [coins, setCoins] = useState('')
  const [total, setTotal] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)                

  const coinsOk = coins === '' || MONEY_OK.test(coins)
  const totalOk = MONEY_OK.test(total)

  const breakdownCents =
    BILLS.reduce((sum, d) => sum + parseInt(counts[d] || '0', 10) * Number(d) * 100, 0) +
    (coins !== '' && coinsOk ? toCents(coins) : 0)
  const countedCents = mode === 'breakdown' ? breakdownCents : totalOk ? toCents(total) : 0

  async function handleSubmit(event) {
    event.preventDefault()
    if (busyRef.current) return
    if (mode === 'breakdown' && !coinsOk) return setError('Coins must be an amount like 35.50.')
    if (mode === 'total' && !totalOk) return setError('Enter the counted total (up to 2 decimals).')
    if (needReason && !reason.trim()) return setError('Enter the reason. It is required and saved on the shift.')

    const ok = window.confirm(
      `Submit a count of ${peso(countedCents)}?\n\nThis closes the shift and it cannot be changed afterwards.`
    )
    if (!ok) return

    const payload =
      mode === 'breakdown'
        ? { denominations: { ...Object.fromEntries(BILLS.map((d) => [d, counts[d] || '0'])), coins: coins || '0' } }
        : { counted_cash: total }
    if (needReason) payload.reason = reason.trim()

    busyRef.current = true
    setBusy(true)
    setError('')
    const message = await onSubmit(payload)   // '' means success
    busyRef.current = false
    if (message) {
      setError(message)
      setBusy(false)
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div style={{ display: 'flex', gap: 8, margin: '8px 0' }}>
        <button type="button" onClick={() => setMode('breakdown')} disabled={mode === 'breakdown'} style={{ padding: '6px 12px' }}>
          Count by bills
        </button>
        <button type="button" onClick={() => setMode('total')} disabled={mode === 'total'} style={{ padding: '6px 12px' }}>
          Type the total
        </button>
      </div>

      {mode === 'breakdown' ? (
        <div>
          {BILLS.map((d) => (
            <label key={d} style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '6px 0' }}>
              <span style={{ width: 90 }}>{PESO}{d} bills</span>
              <input
                style={input}
                inputMode="numeric"
                value={counts[d] ?? ''}
                onChange={(e) => setCounts({ ...counts, [d]: e.target.value.replace(/\D/g, '').slice(0, 6) })}
                placeholder="0"
              />
              <span style={{ color: '#555' }}>= {peso(parseInt(counts[d] || '0', 10) * Number(d) * 100)}</span>
            </label>
          ))}
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '6px 0' }}>
            <span style={{ width: 90 }}>All coins</span>
            <input
              style={input}
              inputMode="decimal"
              value={coins}
              onChange={(e) => setCoins(e.target.value.replace(/[^\d.]/g, ''))}
              placeholder="0.00"
            />
            <span style={{ color: '#555' }}>total pesos</span>
          </label>
        </div>
      ) : (
        <label style={{ display: 'block', margin: '8px 0' }}>
          Total cash counted ({PESO})
          <input
            style={{ ...input, width: '100%', fontSize: 22, boxSizing: 'border-box', marginTop: 4 }}
            inputMode="decimal"
            value={total}
            onChange={(e) => setTotal(e.target.value.replace(/[^\d.]/g, ''))}
            placeholder="0.00"
          />
        </label>
      )}

      <div style={{ fontSize: 22, margin: '12px 0' }}>
        Counted: <b>{peso(countedCents)}</b>
      </div>

      {needReason && (
        <label style={{ display: 'block', margin: '8px 0' }}>
          Reason for closing on the cashier's behalf (required)
          <input
            style={{ ...input, width: '100%', boxSizing: 'border-box', marginTop: 4 }}
            maxLength={200}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="For example: cashier went home sick"
          />
        </label>
      )}

      {error && <p style={{ color: 'crimson', fontSize: 16 }}>{error}</p>}

      <button type="submit" disabled={busy} style={{ width: '100%', padding: 14, fontSize: 18 }}>
        {busy ? 'Saving...' : submitLabel}
      </button>
    </form>
  )
}

const input = { padding: 8, fontSize: 16, width: 110 }