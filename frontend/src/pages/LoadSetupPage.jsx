import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../api'
import { PESO, flattenErrors } from '../utils'

const MONEY_OK = /^\d+(\.\d{1,2})?$/

export default function LoadSetupPage() {
  const [networks, setNetworks] = useState([])
  const [products, setProducts] = useState([])
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(null)   // 'n-ID' or 'p-ID'

  const load = useCallback(async () => {
    try {
      const [n, p] = await Promise.all([apiFetch('/owner/load-networks/'), apiFetch('/owner/load-products/')])
      if (n.ok && p.ok) {
        setNetworks(await n.json())
        setProducts(await p.json())
        setError('')
      } else if (n.status !== 401 && p.status !== 401) {
        setError('Could not load the setup. Please try again.')
      }
    } catch {
      setError('Cannot reach the server. Is Django running?')
    }
  }, [])

  useEffect(() => { load() }, [load])

  // One helper for every change. Returns '' on success, or a message to show.
  async function send(path, method, body) {
    try {
      const response = await apiFetch(path, { method, body: JSON.stringify(body) })
      if (response.ok) {
        await load()
        setEditing(null)
        return ''
      }
      if (response.status === 400) return flattenErrors(await response.json()).join(' ')
      if (response.status === 401) return 'Your session ended. Please log in again.'
      return 'Something went wrong. Please try again.'
    } catch {
      return 'Cannot reach the server. Is Django running?'
    }
  }

  return (
    <div style={{ maxWidth: 1000 }}>
      <h1>Load setup</h1>
      <p style={{ color: '#555' }}>
        <b>Rebate</b> is the discount the provider gives you, as a percent of the load amount. Cashiers never see it.
        To find it: if a {PESO}100 load costs you {PESO}96 in the retailer app, the rebate is 4%. It starts at 0%.
      </p>
      {error && <p style={{ color: 'crimson', fontSize: 18 }}>{error}</p>}

      <h2>Networks</h2>
      <table style={table}>
        <thead><tr style={head}><th style={cell}>Network</th><th style={cell}>Rebate %</th><th style={cell}>Status</th><th style={cell}></th></tr></thead>
        <tbody>
          {networks.map((n) => (
            editing === `n-${n.id}` ? (
              <NetworkEdit key={n.id} network={n} onCancel={() => setEditing(null)} onSave={(body) => send(`/owner/load-networks/${n.id}/`, 'PATCH', body)} />
            ) : (
              <tr key={n.id} style={{ borderBottom: '1px solid #ddd', opacity: n.is_active ? 1 : 0.5 }}>
                <td style={cell}><b>{n.name}</b></td><td style={cell}>{n.rebate_percent}%</td>
                <td style={cell}>{n.is_active ? 'Active' : 'Inactive'}</td>
                <td style={cell}><button onClick={() => setEditing(`n-${n.id}`)} style={{ padding: '6px 10px' }}>Edit</button></td>
              </tr>
            )
          ))}
        </tbody>
      </table>
      <AddNetwork onSave={(body) => send('/owner/load-networks/', 'POST', body)} />

      <h2 style={{ marginTop: 28 }}>Load products (regular loads and promos)</h2>
      <div style={{ overflowX: 'auto' }}>
        <table style={table}>
          <thead>
            <tr style={head}>
              <th style={cell}>Network</th><th style={cell}>Name</th><th style={cell}>Amount sent</th>
              <th style={cell}>Selling price</th><th style={cell}>You gain per load</th><th style={cell}>Status</th><th style={cell}></th>
            </tr>
          </thead>
          <tbody>
            {products.map((p) => {
              const net = networks.find((n) => n.id === p.network)
              const gain = parseFloat(p.selling_price) - parseFloat(p.face_value) + (parseFloat(p.face_value) * parseFloat(net?.rebate_percent ?? 0)) / 100
              return editing === `p-${p.id}` ? (
                <ProductEdit key={p.id} product={p} onCancel={() => setEditing(null)} onSave={(body) => send(`/owner/load-products/${p.id}/`, 'PATCH', body)} />
              ) : (
                <tr key={p.id} style={{ borderBottom: '1px solid #ddd', opacity: p.is_active ? 1 : 0.5 }}>
                  <td style={cell}>{net?.name}</td><td style={cell}><b>{p.name}</b></td>
                  <td style={cell}>{PESO}{p.face_value}</td><td style={cell}>{PESO}{p.selling_price}</td>
                  <td style={{ ...cell, color: gain < 0 ? '#c0392b' : undefined }}>{PESO}{gain.toFixed(2)}</td>
                  <td style={cell}>{p.is_active ? 'Active' : 'Inactive'}</td>
                  <td style={cell}><button onClick={() => setEditing(`p-${p.id}`)} style={{ padding: '6px 10px' }}>Edit</button></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <AddProduct networks={networks} onSave={(body) => send('/owner/load-products/', 'POST', body)} />
    </div>
  )
}

function NetworkEdit({ network, onSave, onCancel }) {
  const [rebate, setRebate] = useState(network.rebate_percent)
  const [active, setActive] = useState(network.is_active)
  const [error, setError] = useState('')
  async function save() {
    if (!MONEY_OK.test(rebate) || parseFloat(rebate) > 100) return setError('Rebate: 0 to 100, up to 2 decimals.')
    setError(await onSave({ rebate_percent: rebate, is_active: active }))
  }
  return (
    <tr style={{ background: '#fafafa' }}>
      <td style={cell}><b>{network.name}</b></td>
      <td style={cell}><input style={small} inputMode="decimal" value={rebate} onChange={(e) => setRebate(e.target.value.replace(/[^\d.]/g, ''))} /></td>
      <td style={cell}><label><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Active</label></td>
      <td style={cell}>
        <button onClick={save} style={{ padding: '6px 10px' }}>Save</button>{' '}
        <button onClick={onCancel} style={{ padding: '6px 10px' }}>Cancel</button>
        {error && <div style={{ color: 'crimson' }}>{error}</div>}
      </td>
    </tr>
  )
}

function ProductEdit({ product, onSave, onCancel }) {
  const [name, setName] = useState(product.name)
  const [face, setFace] = useState(product.face_value)
  const [price, setPrice] = useState(product.selling_price)
  const [active, setActive] = useState(product.is_active)
  const [error, setError] = useState('')
  async function save() {
    if (!name.trim()) return setError('Enter the name.')
    if (!MONEY_OK.test(face) || parseFloat(face) <= 0) return setError('Amount sent: more than 0.')
    if (!MONEY_OK.test(price)) return setError('Selling price: up to 2 decimals.')
    setError(await onSave({ name: name.trim(), face_value: face, selling_price: price, is_active: active }))
  }
  return (
    <tr style={{ background: '#fafafa' }}>
      <td style={cell}></td>
      <td style={cell}><input style={{ ...small, width: 120 }} value={name} onChange={(e) => setName(e.target.value)} /></td>
      <td style={cell}><input style={small} inputMode="decimal" value={face} onChange={(e) => setFace(e.target.value.replace(/[^\d.]/g, ''))} /></td>
      <td style={cell}><input style={small} inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value.replace(/[^\d.]/g, ''))} /></td>
      <td style={cell}></td>
      <td style={cell}><label><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Active</label></td>
      <td style={cell}>
        <button onClick={save} style={{ padding: '6px 10px' }}>Save</button>{' '}
        <button onClick={onCancel} style={{ padding: '6px 10px' }}>Cancel</button>
        {error && <div style={{ color: 'crimson' }}>{error}</div>}
      </td>
    </tr>
  )
}

function AddNetwork({ onSave }) {
  const [name, setName] = useState('')
  const [rebate, setRebate] = useState('0')
  const [error, setError] = useState('')
  async function submit(event) {
    event.preventDefault()
    if (!name.trim()) return setError('Enter the network name.')
    if (!MONEY_OK.test(rebate) || parseFloat(rebate) > 100) return setError('Rebate: 0 to 100, up to 2 decimals.')
    const message = await onSave({ name: name.trim(), rebate_percent: rebate })
    setError(message)
    if (!message) { setName(''); setRebate('0') }
  }
  return (
    <form onSubmit={submit} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', margin: '10px 0' }}>
      <input style={{ ...small, width: 160 }} value={name} onChange={(e) => setName(e.target.value)} placeholder="New network" />
      <input style={small} inputMode="decimal" value={rebate} onChange={(e) => setRebate(e.target.value.replace(/[^\d.]/g, ''))} title="Rebate %" />%
      <button type="submit" style={{ padding: '8px 12px' }}>+ Add network</button>
      {error && <span style={{ color: 'crimson' }}>{error}</span>}
    </form>
  )
}

function AddProduct({ networks, onSave }) {
  const [network, setNetwork] = useState('')
  const [name, setName] = useState('')
  const [face, setFace] = useState('')
  const [price, setPrice] = useState('')
  const [error, setError] = useState('')
  async function submit(event) {
    event.preventDefault()
    if (!network) return setError('Choose the network.')
    if (!name.trim()) return setError('Enter the name (for example Load 50 or EZ50).')
    if (!MONEY_OK.test(face) || parseFloat(face) <= 0) return setError('Amount sent: more than 0.')
    if (!MONEY_OK.test(price)) return setError('Enter the selling price.')
    const message = await onSave({ network: Number(network), name: name.trim(), face_value: face, selling_price: price })
    setError(message)
    if (!message) { setName(''); setFace(''); setPrice('') }
  }
  return (
    <form onSubmit={submit} style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', margin: '10px 0' }}>
      <select style={small} value={network} onChange={(e) => setNetwork(e.target.value)}>
        <option value="">Network...</option>
        {networks.map((n) => <option key={n.id} value={n.id}>{n.name}</option>)}
      </select>
      <input style={{ ...small, width: 130 }} value={name} onChange={(e) => setName(e.target.value)} placeholder="Name, e.g. EZ50" />
      <input style={small} inputMode="decimal" value={face} onChange={(e) => setFace(e.target.value.replace(/[^\d.]/g, ''))} placeholder="Amount sent" />
      <input style={small} inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value.replace(/[^\d.]/g, ''))} placeholder="Selling price" />
      <button type="submit" style={{ padding: '8px 12px' }}>+ Add product</button>
      {error && <span style={{ color: 'crimson' }}>{error}</span>}
    </form>
  )
}

const table = { borderCollapse: 'collapse', width: '100%', minWidth: 560 }
const head = { textAlign: 'left', borderBottom: '2px solid #333' }
const cell = { padding: '8px 10px', verticalAlign: 'top' }
const small = { padding: 8, fontSize: 16, width: 100 }