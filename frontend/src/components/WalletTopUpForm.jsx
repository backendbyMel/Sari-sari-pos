import { useRef, useState } from 'react'
import { apiFetch } from '../api'
import { PESO, flattenErrors } from '../utils'

const MONEY_OK = /^\d+(\.\d{1,2})?$/  

export default function WalletTopUpForm({ sources, onDone, kind = 'load', title = 'load wallet' }) {
  const [added, setAdded] = useState('')
  const [paid, setPaid] = useState('')
  const [paidTouched, setPaidTouched] = useState(false)
  const [source, setSource] = useState(sources[0][0])
  const [reference, setReference] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)   

  const shownPaid = paidTouched ? paid : added   

  async function handleSubmit(event) {
    event.preventDefault()
    if (busyRef.current) return
    if (!MONEY_OK.test(added) || parseFloat(added) <= 0) return setError('Enter the amount added to the wallet.')
    if (!MONEY_OK.test(shownPaid)) return setError('Enter the amount you paid (up to 2 decimals).')
    const ok = window.confirm(
      `Add ${PESO}${Number(added).toFixed(2)} to the ${title}?\n` +
      `You paid ${PESO}${Number(shownPaid).toFixed(2)} (${sources.find((s) => s[0] === source)[1]}).\n\n` +
      'It is saved under your name and cannot be edited.'
    )
    if (!ok) return

    busyRef.current = true
    setBusy(true)
    setError('')
    try {
      const response = await apiFetch(`/wallets/topup/?kind=${kind}`, {
        method: 'POST',
        body: JSON.stringify({ amount_added: added, amount_paid: shownPaid, source, reference_no: reference.trim() }),
      })
      if (response.status === 201) {
        const data = await response.json()
        setAdded('')
        setPaid('')
        setPaidTouched(false)
        setReference('')
        onDone(data.warnings.length > 0 ? `Top-up recorded. Note: ${data.warnings.join(' ')}` : 'Top-up recorded.')
      } else if (response.status === 400 || response.status === 403) {
        setError(flattenErrors(await response.json()).join(' '))
      } else if (response.status !== 401) {
        setError('Something went wrong. Check the history before trying again.')
      }
    } catch {
      setError('Connection lost. The top-up may or may not have been saved. Check the history BEFORE trying again.')
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ border: '1px solid #999', borderRadius: 8, padding: 14, background: '#fafafa' }}>
      <b>Top up the {title}</b>
      <label style={{ display: 'block', marginTop: 8 }}>
        Amount added to the wallet ({PESO})
        <input style={field} inputMode="decimal" value={added}
               onChange={(e) => setAdded(e.target.value.replace(/[^\d.]/g, ''))} placeholder="1000.00" />
      </label>
      <label style={{ display: 'block', marginTop: 8 }}>
        Amount you paid ({PESO})
        <input style={field} inputMode="decimal" value={shownPaid}
               onChange={(e) => { setPaid(e.target.value.replace(/[^\d.]/g, '')); setPaidTouched(true) }} />
      </label>
      <label style={{ display: 'block', marginTop: 8 }}>
        Where the money came from
        <select style={field} value={source} onChange={(e) => setSource(e.target.value)}>
          {sources.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label style={{ display: 'block', marginTop: 8 }}>
        Reference number (optional)
        <input style={field} maxLength={50} value={reference} onChange={(e) => setReference(e.target.value)} />
      </label>
      {error && <p style={{ color: 'crimson' }}>{error}</p>}
      <button type="submit" disabled={busy} style={{ width: '100%', padding: 12, fontSize: 16, marginTop: 10 }}>
        {busy ? 'Saving...' : 'Record top-up'}
      </button>
    </form>
  )
}

const field = { display: 'block', width: '100%', padding: 10, marginTop: 4, fontSize: 16, boxSizing: 'border-box' }