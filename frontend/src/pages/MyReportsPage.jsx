import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../api'
import PdfPreview from '../components/PdfPreview'
import { PESO, formatTime, signedPeso, toCents } from '../utils'

const color = (v) => (parseFloat(v) < 0 ? '#c0392b' : parseFloat(v) > 0 ? '#b86e00' : '#1b7f3b')

export default function MyReportsPage() {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [preview, setPreview] = useState(null)   // { shiftId, filename }

  useEffect(() => {
    async function load() {
      try {
        const response = await apiFetch('/shifts/mine/')
        if (response.ok) setRows(await response.json())
        else if (response.status !== 401) setError('Could not load your reports. Please try again.')
      } catch {
        setError('Cannot reach the server. Is Django running?')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  return (
    <div style={{ maxWidth: 560, margin: '0 auto', padding: 16, fontFamily: 'sans-serif' }}>
      <p><Link to="/">&larr; Back</Link></p>
      <h1>My Past Reports</h1>
      {loading && <p>Loading...</p>}
      {error && <p style={{ color: 'crimson', fontSize: 18 }}>{error}</p>}
      {!loading && !error && rows.length === 0 && <p style={{ color: '#777' }}>No finished shifts yet.</p>}

      {rows.map((s) => (
        <div key={s.id} style={{ border: '1px solid #ccc', borderRadius: 8, padding: 12, marginBottom: 10 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <b>Shift #{s.id}</b>
            <b style={{ color: color(s.variance) }}>{signedPeso(toCents(s.variance))}</b>
          </div>
          <div style={{ color: '#555' }}>{formatTime(s.start_time)} to {formatTime(s.end_time)}</div>
          <div>Counted {PESO}{s.counted_cash}</div>
          {s.closed_on_behalf && <small style={{ color: '#b86e00' }}>Closed by {s.closed_by} on your behalf.</small>}
          <div style={{ marginTop: 6 }}>
            {s.report ? (
              <button
                onClick={() => setPreview({ shiftId: s.id, filename: `${s.report.report_no}-cashier.pdf` })}
                style={{ padding: '8px 14px' }}
              >
                View report {s.report.report_no}
              </button>
            ) : (
              <small style={{ color: '#777' }}>No report file. Ask the owner.</small>
            )}
          </div>
        </div>
      ))}

      {preview && (
        <PdfPreview shiftId={preview.shiftId} copy="cashier" filename={preview.filename} onClose={() => setPreview(null)} />
      )}
    </div>
  )
}