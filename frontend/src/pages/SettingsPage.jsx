import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api'
import { PESO, flattenErrors } from '../utils'

const MONEY_OK = /^\d+(\.\d{1,2})?$/   

export default function SettingsPage() {
  const [minutes, setMinutes] = useState('')
  const [limit, setLimit] = useState('')
  const [mode, setMode] = useState('warn')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)  
  const [overdue, setOverdue] = useState('')
  const [topUp, setTopUp] = useState(false)

  function show(data) {
    setMinutes(String(data.idle_logout_minutes))
    setLimit(data.default_credit_limit)
    setMode(data.credit_limit_mode)
    setOverdue(String(data.overdue_days))
    setTopUp(data.cashier_can_topup)
  }

  useEffect(() => {
    async function load() {
      try {
        const response = await apiFetch('/settings/')
        if (response.ok) show(await response.json())
        else if (response.status !== 401) setError('Could not load the settings. Please try again.')
      } catch {
        setError('Cannot reach the server. Is Django running?')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  async function handleSubmit(event) {
    event.preventDefault()
    if (busyRef.current) return
    if (!/^\d{1,3}$/.test(minutes) || Number(minutes) < 1 || Number(minutes) > 240) {
      return setError('Automatic logout: enter a whole number of minutes from 1 to 240.')
    }
    if (!MONEY_OK.test(limit)) return setError('Credit limit: enter an amount (0 or more, up to 2 decimals).')
    if (!/^\d{1,3}$/.test(overdue) || Number(overdue) < 1 || Number(overdue) > 365) {
      return setError('Overdue days: enter a whole number from 1 to 365.')
    }

    busyRef.current = true
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const response = await apiFetch('/settings/', {
        method: 'PATCH',
        body: JSON.stringify({
          idle_logout_minutes: Number(minutes),
          default_credit_limit: limit,
          credit_limit_mode: mode,
          overdue_days: Number(overdue),
          cashier_can_topup: topUp,
        }),
      })
      if (response.ok) {
        show(await response.json())
        setNotice('Saved. The new credit rules apply to the very next sale. The logout time reaches others at their next login.')
        window.dispatchEvent(new Event('settings-changed'))
      } else if (response.status === 400) {
        setError(flattenErrors(await response.json()).join(' '))
      } else if (response.status !== 401) {
        setError('Something went wrong. Please try again.')
      }
    } catch {
      setError('Cannot reach the server. Is Django running?')
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  return (
    <div style={{ maxWidth: 560 }}>
      <h1>Settings</h1>
      {loading && <p>Loading...</p>}
      {!loading && (
        <form onSubmit={handleSubmit}>
          <div style={box}>
            <h2 style={{ marginTop: 0 }}>Automatic logout</h2>
            <label>
              Log out after this many idle minutes
              <input
                style={{ display: 'block', width: 140, padding: 10, marginTop: 4, fontSize: 18 }}
                inputMode="numeric"
                value={minutes}
                onChange={(e) => setMinutes(e.target.value.replace(/\D/g, '').slice(0, 3))}
              />
            </label>
            <p style={{ color: '#555' }}>
              From 1 to 240. A warning appears for the last minute. Logging out never ends a shift,
              but an unfinished held sale is lost.
            </p>
          </div>

          <div style={box}>
            <h2 style={{ marginTop: 0 }}>Utang (credit)</h2>
            <label>
              Default credit limit per customer ({PESO})
              <input
                style={{ display: 'block', width: 180, padding: 10, marginTop: 4, fontSize: 18 }}
                inputMode="decimal"
                value={limit}
                onChange={(e) => setLimit(e.target.value.replace(/[^\d.]/g, ''))}
              />
            </label>
            <p style={{ margin: '14px 0 4px' }}>When a sale would pass the limit:</p>
            <label style={{ display: 'block' }}>
              <input type="radio" name="mode" checked={mode === 'warn'} onChange={() => setMode('warn')} />{' '}
              <b>Warn</b>: the cashier sees the balance and may confirm
            </label>
            <label style={{ display: 'block' }}>
              <input type="radio" name="mode" checked={mode === 'block'} onChange={() => setMode('block')} />{' '}
              <b>Block</b>: the sale is refused
            </label>
            <label style={{ display: 'block', marginTop: 14 }}>
              A balance is overdue when its oldest unpaid charge is older than (days)
              <input
                style={{ display: 'block', width: 140, padding: 10, marginTop: 4, fontSize: 18 }}
                inputMode="numeric"
                value={overdue}
                onChange={(e) => setOverdue(e.target.value.replace(/\D/g, '').slice(0, 3))}
              />
            </label>
          </div>
          <div style={box}>
            <h2 style={{ marginTop: 0 }}>Mobile load</h2>
            <label>
              <input type="checkbox" checked={topUp} onChange={(e) => setTopUp(e.target.checked)} />{' '}
              Cashiers may top up the load wallet with <b>cash from the drawer</b>
            </label>
            <p style={{ color: '#555', marginBottom: 0 }}>
              Off by default. The money leaving the drawer is saved as a pay-out in their shift.
            </p>
          </div>
          {error && <p style={{ color: 'crimson', fontSize: 16 }}>{error}</p>}
          {notice && <p style={{ background: '#f3fbf5', border: '1px solid #1b7f3b', padding: 10, borderRadius: 6 }}>{notice}</p>}
          <button type="submit" disabled={busy} style={{ padding: '10px 18px', fontSize: 16 }}>
            {busy ? 'Saving...' : 'Save'}
          </button>
        </form>
      )}
      <p style={{ color: '#777' }}>
        More settings (store name, receipt text, discount limit, fees) arrive in later steps.
      </p>
    </div>
  )
}

const box = { border: '1px solid #999', borderRadius: 8, padding: 16, background: '#fafafa', marginBottom: 16 }