import ExportButtons from '../components/ExportButtons'
import { useReport } from './ReportsPage'
import { formatTime } from '../utils'

export default function ShoppingListPage() {
  const state = useReport('shopping-list', {})
  const { data } = state

  return (
    <div style={{ maxWidth: 900 }}>
      <h1>Shopping list</h1>
      <p style={{ color: '#555' }}>
        Items at or below their low-stock level. Print it or download it, then write the quantity to buy.
        Quantities are in each product's smallest unit.
      </p>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <button onClick={() => window.print()} disabled={!data || data.count === 0} style={{ padding: '8px 16px', fontSize: 16 }}>
          Print
        </button>
        <ExportButtons path="/owner/exports/shopping-list/" name={`shopping-list-${data?.date ?? 'today'}`} />
      </div>

      {state.loading && !data && <p>Loading...</p>}
      {state.error && <p style={{ color: 'crimson', fontSize: 18 }}>{state.error}</p>}
      {data && data.count === 0 && <p style={{ color: '#1b7f3b', fontSize: 18 }}>Nothing is low. No shopping needed.</p>}

      {data && data.count > 0 && (
        <div className="print-area" style={{ background: '#fff', padding: 8 }}>
          <h2 style={{ marginTop: 0 }}>Shopping list, {data.date}</h2>
          <table style={{ borderCollapse: 'collapse', width: '100%' }}>
            <thead>
              <tr style={{ textAlign: 'left', borderBottom: '2px solid #333' }}>
                <th style={cell}>Product</th><th style={cell}>Category</th><th style={cell}>In stock</th>
                <th style={cell}>Level</th><th style={cell}>Last bought</th><th style={{ ...cell, width: 110 }}>To buy</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((i) => (
                <tr key={i.id} style={{ borderBottom: '1px solid #999' }}>
                  <td style={cell}>
                    <b>{i.name}</b>
                    {i.needs_recount && <small style={{ color: '#b86e00' }}> recount first</small>}
                  </td>
                  <td style={cell}>{i.category}</td>
                  <td style={{ ...cell, color: i.status === 'out' ? '#c0392b' : '#b86e00', fontWeight: 'bold' }}>
                    {i.stock} {i.unit} {i.status === 'out' && '(OUT)'}
                  </td>
                  <td style={cell}>{i.low_level}</td>
                  <td style={cell}>
                    {i.last_bought ? `${i.last_bought} (${i.last_quantity})` : 'Never'}
                  </td>
                  <td style={{ ...cell, height: 36 }}><div style={{ border: '1px solid #666', height: 28 }} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && <small style={{ color: '#777' }}>Made {formatTime(new Date().toISOString())}.</small>}
    </div>
  )
}

const cell = { padding: '8px 10px', verticalAlign: 'middle' }