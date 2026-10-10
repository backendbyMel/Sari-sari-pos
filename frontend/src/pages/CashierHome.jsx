import { useState } from 'react'
import { apiFetch } from '../api'
import { useAuth } from '../AuthContext'
import { Link } from 'react-router-dom'
import { useCurrentShift } from '../useCurrentShift'
import { formatTime } from '../utils'

export default function CashierHome() {
  const { user, logout } = useAuth()
  const { loading, error, shift, isMine } = useCurrentShift()

  return (
    <div style={{ maxWidth: 520, margin: '0 auto', padding: 16, fontFamily: 'sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 style={{ margin: 0 }}>Cashier</h1>
        <span>{user.username} <button onClick={logout} style={{ marginLeft: 8 }}>Log out</button></span>
      </div>

      <div style={{ border: '1px solid #ccc', borderRadius: 8, padding: 14, margin: '16px 0' }}>
        <b>Shift</b>
        {loading && <p style={{ margin: '6px 0 0' }}>Checking...</p>}
        {error && <p style={{ margin: '6px 0 0', color: 'crimson' }}>{error}</p>}
        {!loading && !error && !shift && (
          <>
            <p style={{ margin: '6px 0 10px' }}>No shift is open.</p>
            <Link to="/shift/start"><b>Start shift</b></Link>
          </>
        )}
        {!loading && !error && shift && isMine && (
          <>
            <p style={{ margin: '6px 0 10px', color: '#1b7f3b' }}>
              Your shift is open (since {formatTime(shift.start_time)}).
            </p>
            <Link to="/shift/summary"><b>Shift summary and pay-outs</b></Link>
            <br />
            <Link to="/shift/end"><b>End shift</b></Link>
          </>
        )}
        {!loading && !error && shift && !isMine && (
          <p style={{ margin: '6px 0 0', color: '#b86e00' }}>
            {shift.cashier} has the shift open (since {formatTime(shift.start_time)}).
          </p>
        )}
      </div>

      <p style={{ fontSize: 20 }}><Link to="/sales"><b>Sales</b></Link></p>
      <p style={{ fontSize: 20 }}><Link to="/receipts">Receipts (reprint)</Link></p>
      <p style={{ fontSize: 20 }}><Link to="/customers">Utang customers</Link></p>
      <p style={{ fontSize: 20 }}><Link to="/load">Mobile load</Link></p>
      <p style={{ fontSize: 20 }}><Link to="/gcash">GCash cash in / out</Link></p>
      <p style={{ fontSize: 20 }}><Link to="/price-check">Price Check</Link></p>
      <p style={{ fontSize: 20 }}><Link to="/reports/mine">My past reports</Link></p>
    </div>
  )
}