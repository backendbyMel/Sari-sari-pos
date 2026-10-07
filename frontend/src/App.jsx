import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './AuthContext'
import ProtectedRoute from './ProtectedRoute'
import CashierHome from './pages/CashierHome'
import LoginPage from './pages/LoginPage'
import OwnerHome from './pages/OwnerHome'

function HomeRedirect() {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  return <Navigate to={user.role === 'OWNER' ? '/owner' : '/cashier'} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/owner" element={<ProtectedRoute role="OWNER"><OwnerHome /></ProtectedRoute>} />
      <Route path="/cashier" element={<ProtectedRoute><CashierHome /></ProtectedRoute>} />
      <Route path="/" element={<HomeRedirect />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}