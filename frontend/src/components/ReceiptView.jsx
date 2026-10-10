import { PESO } from '../utils'

export default function ReceiptView({ receipt }) {
  const r = receipt
  const isPayment = r.kind === 'utang_payment'
  const isLoad = r.kind === 'load'
  const isEwallet = r.kind === 'ewallet'
  const isUtang = r.payment_type === 'utang'

  return (
    <div
      className="receipt-print"
      style={{
        fontFamily: 'monospace', fontSize: 14, width: 300, maxWidth: '100%',
        padding: 12, boxSizing: 'border-box', background: '#fff', color: '#000',
      }}
    >
      {r.is_void && <Banner text="*** VOID ***" />}
      {r.is_failed && <Banner text="*** FAILED - REFUNDED ***" />}
      {r.is_reversed && <Banner text="*** REVERSED ***" />}
      {r.is_copy && <Banner text="*** COPY ***" />}

      <div style={{ textAlign: 'center' }}>
        <b>{r.store.name}</b><br />
        {r.store.address}<br />
        {r.store.contact}
      </div>
      <Line />
      {isPayment && <div style={{ textAlign: 'center', fontWeight: 'bold' }}>UTANG PAYMENT</div>}
      {isLoad && <div style={{ textAlign: 'center', fontWeight: 'bold' }}>MOBILE LOAD</div>}
      {isEwallet && (
        <div style={{ textAlign: 'center', fontWeight: 'bold' }}>
          {r.ewallet.service.toUpperCase()} {r.ewallet.type === 'cash_in' ? 'CASH IN' : 'CASH OUT'}
        </div>
      )}
      <div>Receipt: {r.receipt_no}</div>
      <div>{r.date_time}</div>
      <div>Cashier: {r.cashier}</div>
      {r.customer && <div>Customer: {r.customer.name}</div>}
      <Line />

      {isLoad && (
        <>
          <Row label="Network" value={r.load.network} />
          <Row label="Load" value={r.load.product} />
          <Row label="Number" value={r.load.mobile} />
          <Row label="Reference" value={r.load.reference_no} />
          <Line />
        </>
      )}

      {isEwallet && (
        <>
          <Row label="Number" value={r.ewallet.mobile} />
          <Row label="Reference" value={r.ewallet.reference_no} />
          <Row label="Amount" value={`${PESO}${r.ewallet.amount}`} />
          <Row label="Fee" value={`${PESO}${r.ewallet.fee}`} />
          <Line />
        </>
      )}

      {r.items.map((item, index) => (
        <div key={index} style={{ marginBottom: 6 }}>
          <div>{item.name}</div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>{item.quantity} {item.unit} x {item.price}</span>
            <span>{item.line_total}</span>
          </div>
        </div>
      ))}
      {r.items.length > 0 && <Line />}

      {isPayment ? (
        <>
          <Row label="PAID" value={`${PESO}${r.total}`} bold />
          <Row label="Remaining balance" value={`${PESO}${r.balance_after}`} />
        </>
      ) : isLoad ? (
        <Row label="PAID (cash)" value={`${PESO}${r.total}`} bold />
      ) : isEwallet ? (
        <Row
          label={r.ewallet.type === 'cash_in' ? 'CUSTOMER PAID' : 'CASH GIVEN'}
          value={`${PESO}${r.total}`}
          bold
        />
      ) : (
        <>
          {Number(r.discount) > 0 && <Row label="Discount" value={`-${r.discount}`} />}
          <Row label="TOTAL" value={`${PESO}${r.total}`} bold />
          {isUtang ? (
            <>
              <Row label="Payment" value="UTANG" />
              <Row label="Balance now" value={`${PESO}${r.balance_after}`} />
            </>
          ) : (
            <>
              <Row label="Cash" value={r.cash_received} />
              <Row label="Change" value={r.change} />
            </>
          )}
        </>
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