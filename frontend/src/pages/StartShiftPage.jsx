import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { apiFetch } from '../api'
import { useCurrentShift } from '../useCurrentShift'
import { PESO, flattenErrors, formatTime } from '../utils'
import WalletBalanceFields, { walletsOk } from '../components/WalletBalanceFields'
import { useWalletsToCheck } from '../useWalletsToCheck'

const MONEY_OK = /^\d+(\.\d{1,2})?$/   

export default function StartShiftPage() {
  const { loading, error, shift, isMine } = useCurrentShift()

  return (
    <div style={{ maxWidth: 480, margin: '0 auto', padding: 16, fontFamily: 'sans-serif' }}>
      <p><Link to="/">&larr; Back</Link></p>
      <h1>Start Shift</h1>

      {loading && <p>Loading...</p>}
      {error && <p style={{ color: 'crimson', fontSize: 18 }}>{error}</p>}

      {!loading && !error && shift && (
        <div style={{ background: '#fff3cd', padding: 14, borderRadius: 8 }}>
          {isMine ? (
            <>
              <p style={{ marginTop: 0 }}>
                You already have an open shift (started {formatTime(shift.start_time)}).
              </p>
              <Link to="/sales"><b>Go to Sales</b></Link>
            </>
          ) : (
            <p style={{ margin: 0 }}>
              <b>{shift.cashier}</b> still has a shift open (since {formatTime(shift.start_time)}).
              It must be ended before you can start yours. Please ask the owner.
            </p>
          )}
        </div>
      )}

      {!loading && !error && !shift && <StartForm />}
    </div>
  )
}

function StartForm() {
  const navigate = useNavigate()
  const { wallets, error: walletError } = useWalletsToCheck()
  const [cash, setCash] = useState('')
  const [balances, setBalances] = useState({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)   

  async function handleSubmit(event) {
    event.preventDefault()
    if (busyRef.current || !wallets) return
    if (!MONEY_OK.test(cash)) {
      return setError('Enter the cash you counted (0 or more, up to 2 decimals).')
    }
    if (!walletsOk(wallets, balances)) {
      return setError('Type the balance shown in each app (up to 2 decimals).')
    }
    const ok = window.confirm(
      `Start your shift with ${PESO}${Number(cash).toFixed(2)} in the drawer?\n\n` +
      'The cash and the app balances cannot be changed afterwards.'
    )
    if (!ok) return

    busyRef.current = true
    setBusy(true)
    setError('')
    try {
      const response = await apiFetch('/shifts/start/', {
        method: 'POST',
        body: JSON.stringify({ opening_cash: cash, wallet_balances: balances }),
      })
      if (response.status === 201) {
        navigate('/sales', { replace: true })
        return
      }
      if (response.status === 400) setError(flattenErrors(await response.json()).join(' '))
      else if (response.status !== 401) setError('Something went wrong. Check your shift status before trying again.')
    } catch {
      setError('Connection lost. Your shift may have started. Go back and check before trying again.')
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  if (walletError) return <p style={{ color: 'crimson', fontSize: 18 }}>{walletError}</p>
  if (!wallets) return <p>Loading...</p>

  return (
    <form onSubmit={handleSubmit}>
      <p style={{ color: '#555' }}>
        Count the money in the drawer and type <b>exactly what you counted</b>. Do not guess.
        The owner compares it with the last shift's closing count.
      </p>
      <label>
        Cash in the drawer ({PESO})
        <input
          style={{ display: 'block', width: '100%', padding: 14, fontSize: 22, boxSizing: 'border-box', marginTop: 4 }}
          inputMode="decimal"
          value={cash}
          onChange={(e) => setCash(e.target.value.replace(/[^\d.]/g, ''))}
          placeholder="0.00"
          autoFocus
        />
      </label>
      <WalletBalanceFields wallets={wallets} balances={balances} onChange={setBalances} />
      {error && <p style={{ color: 'crimson', fontSize: 16 }}>{error}</p>}
      <button type="submit" disabled={busy} style={{ width: '100%', padding: 16, fontSize: 18, marginTop: 12 }}>
        {busy ? 'Starting...' : 'Start shift'}
      </button>
    </form>
  )
}