import { PESO } from '../utils'
export default function ReceiptView({ receipt }) {
  const r = receipt
  const isCash = r.payment_type === 'cash'

  return (
    <div
      className="receipt-print"
      style={{
        fontFamily: 'monospace', fontSize: 14, width: 300, maxWidth: '100%',
        padding: 12, boxSizing: 'border-box', background: '#fff', color: '#000',
      }}
    >
      {r.is_void && <Banner text="*** VOID ***" />}
      {r.is_copy && <Banner text="*** COPY ***" />}

      <div style={{ textAlign: 'center' }}>
        <b>{r.store.name}</b><br />
        {r.store.address}<br />
        {r.store.contact}
      </div>
      <Line />
      <div>Receipt: {r.receipt_no}</div>
      <div>{r.date_time}</div>
      <div>Cashier: {r.cashier}</div>
      <Line />

      {r.items.map((item, index) => (
        <div key={index} style={{ marginBottom: 6 }}>
          <div>{item.name}</div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>{item.quantity} {item.unit} x {item.price}</span>
            <span>{item.line_total}</span>
          </div>
        </div>
      ))}
      <Line />

      {Number(r.discount) > 0 && <Row label="Discount" value={`-${r.discount}`} />}
      <Row label="TOTAL" value={`${PESO}${r.total}`} bold />
      {isCash ? (
        <>
          <Row label="Cash" value={r.cash_received} />
          <Row label="Change" value={r.change} />
        </>
      ) : (
        <Row label="Payment" value="Utang" />
      )}
    </div>
  )
}

function Line() {
  return <hr style={{ border: 'none', borderTop: '1px dashed #000', margin: '8px 0' }} />
}

function Row({ label, value, bold }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: bold ? 'bold' : 'normal' }}>
      <span>{label}</span>
      <span>{value}</span>
    </div>
  )
}

function Banner({ text }) {
  return <div style={{ textAlign: 'center', fontWeight: 'bold', fontSize: 18, marginBottom: 6 }}>{text}</div>
}