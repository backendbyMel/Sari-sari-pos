import { useState } from 'react'
import { downloadFile } from '../download'

export default function ExportButtons({ path, params = {}, name, label = 'Download' }) {
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  async function go(fmt) {
    if (busy) return
    setBusy(fmt)
    setError('')
    try {
      const query = new URLSearchParams({ ...params, fmt }).toString()
      await downloadFile(`${path}?${query}`, `${name}.${fmt}`)
    } catch (e) {
      setError(e instanceof TypeError ? 'Cannot reach the server. Is Django running?' : e.message)
    } finally {
      setBusy('')
    }
  }

  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', margin: '8px 0' }}>
      <span style={{ color: '#555' }}>{label}:</span>
      <button onClick={() => go('csv')} disabled={busy !== ''} style={{ padding: '6px 12px' }}>
        {busy === 'csv' ? 'Preparing...' : 'CSV (Excel)'}
      </button>
      <button onClick={() => go('pdf')} disabled={busy !== ''} style={{ padding: '6px 12px' }}>
        {busy === 'pdf' ? 'Preparing...' : 'PDF'}
      </button>
      {error && <span style={{ color: 'crimson' }}>{error}</span>}
    </div>
  )
}