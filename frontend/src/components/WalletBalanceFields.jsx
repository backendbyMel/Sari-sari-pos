import { PESO } from '../utils'

const MONEY_OK = /^\d+(\.\d{1,2})?$/   

export const walletsOk = (wallets, balances) =>
  wallets.every((w) => MONEY_OK.test(balances[w.id] ?? ''))

export default function WalletBalanceFields({ wallets, balances, onChange }) {
  if (wallets.length === 0) return null
  return (
    <div style={{ border: '1px solid #999', borderRadius: 8, padding: 12, margin: '12px 0', background: '#fafafa' }}>
      <b>Balances shown in the apps</b>
      <p style={{ color: '#555', margin: '4px 0 8px' }}>
        Open each app and type <b>exactly the balance it shows</b>. Do not guess.
      </p>
      {wallets.map((w) => (
        <label key={w.id} style={{ display: 'block', margin: '8px 0' }}>
          {w.provider} ({PESO})
          <input
            style={{ display: 'block', width: '100%', padding: 10, fontSize: 18, boxSizing: 'border-box', marginTop: 4 }}
            inputMode="decimal"
            value={balances[w.id] ?? ''}
            onChange={(e) => onChange({ ...balances, [w.id]: e.target.value.replace(/[^\d.]/g, '') })}
            placeholder="0.00"
          />
        </label>
      ))}
    </div>
  )
}