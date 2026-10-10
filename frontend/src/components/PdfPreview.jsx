import { useEffect, useState } from 'react'
import { apiFetch } from '../api'

export default function PdfPreview({ shiftId, copy, filename, onClose }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    let objectUrl = ''
    async function load() {
      try {
        const response = await apiFetch(`/shifts/${shiftId}/report/?copy=${copy}`)
        if (cancelled) return
        if (response.ok) {
          objectUrl = URL.createObjectURL(await response.blob())
          if (cancelled) {
            URL.revokeObjectURL(objectUrl)
            return
          }
          setUrl(objectUrl)
        } else if (response.status === 404) {
          setError('This report is not available.')
        } else if (response.status !== 401) {
          setError('Could not load the report. Please try again.')
        }
      } catch {
        if (!cancelled) setError('Cannot reach the server. Is Django running?')
      }
    }
    load()
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)   // free the memory
    }
  }, [shiftId, copy])

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 12, zIndex: 10 }}>
      <div style={{ background: '#fff', borderRadius: 8, width: 'min(900px, 100%)', height: '95vh', display: 'flex', flexDirection: 'column', padding: 12, boxSizing: 'border-box' }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 8, flexWrap: 'wrap' }}>
          <b style={{ flex: 1 }}>{filename}</b>
          {url && (
            <a href={url} download={filename} style={{ padding: '8px 14px', border: '1px solid #767676', borderRadius: 3, background: '#efefef', color: '#000', textDecoration: 'none' }}>
              Download
            </a>
          )}
          <button onClick={onClose} style={{ padding: '8px 14px' }}>Close</button>
        </div>
        {!url && !error && <p>Loading...</p>}
        {error && <p style={{ color: 'crimson', fontSize: 18 }}>{error}</p>}
        {url && (
          <iframe title={filename} src={url} style={{ flex: 1, width: '100%', border: '1px solid #ccc' }} />
        )}
        {url && <small style={{ color: '#777' }}>If the report does not show on your phone, tap Download.</small>}
      </div>
    </div>
  )
}