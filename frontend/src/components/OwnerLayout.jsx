import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../AuthContext'

const LINKS = [
  { to: '/owner', label: 'Home', end: true },
  { to: '/owner/products', label: 'Products' },
  { to: '/owner/restock', label: 'Restock' },
  { to: '/owner/adjustments', label: 'Adjustments' },
  { to: '/owner/stock-history', label: 'Stock History' },
  { to: '/owner/users', label: 'Users' },
  { to: '/owner/shifts', label: 'Shifts' },
  { to: '/owner/shift-reports', label: 'Shift Reports' },
  { to: '/owner/settings', label: 'Settings' },
  { to: '/owner/customers', label: 'Utang' },
  { to: '/owner/wallet', label: 'Load wallet' },
  { to: '/owner/load-setup', label: 'Load setup' },
  { to: '/owner/gcash-wallet', label: 'GCash wallet' },
  { to: '/owner/gcash', label: 'GCash fees' },
]

export default function OwnerLayout() {
  const { user, logout } = useAuth()

  return (
    <div style={{ fontFamily: 'sans-serif' }}>
      <header
        style={{
          display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap',
          padding: '10px 16px', background: '#1f2937', color: '#fff',
        }}
      >
        <b>Sari-Sari POS &middot; Owner</b>
        <nav style={{ display: 'flex', gap: 14, flex: 1, flexWrap: 'wrap' }}>
          {LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              style={({ isActive }) => ({
                color: '#fff',
                fontWeight: isActive ? 'bold' : 'normal',
                textDecoration: isActive ? 'underline' : 'none',
              })}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
        <span>{user.username}</span>
        <button onClick={logout}>Log out</button>
      </header>

      <main style={{ padding: 16 }}>
        <Outlet />
      </main>
    </div>
  )
}