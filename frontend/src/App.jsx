import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './AuthContext'
import ProtectedRoute from './ProtectedRoute'
import CashierHome from './pages/CashierHome'
import LoginPage from './pages/LoginPage'
import OwnerHome from './pages/OwnerHome'
import PriceCheckPage from './pages/PriceCheckPage'
import SalesPage from './pages/SalesPage'
import ReceiptsPage from './pages/ReceiptsPage'
import OwnerLayout from './components/OwnerLayout'
import ProductsPage from './pages/ProductsPage'
import ProductUnitsPage from './pages/ProductUnitsPage'
import RestockPage from './pages/RestockPage'
import AdjustmentsPage from './pages/AdjustmentsPage'
import StockHistoryPage from './pages/StockHistoryPage'
import UsersPage from './pages/UsersPage'
import StartShiftPage from './pages/StartShiftPage'
import EndShiftPage from './pages/EndShiftPage'
import ShiftsPage from './pages/ShiftsPage'
import ShiftSummaryPage from './pages/ShiftSummaryPage'
import MyReportsPage from './pages/MyReportsPage'
import ShiftReportsPage from './pages/ShiftReportsPage'
import IdleGuard from './IdleGuard'
import SettingsPage from './pages/SettingsPage'
import CustomersPage from './pages/CustomersPage'
import OwnerCustomersPage from './pages/OwnerCustomersPage'
import LoadPage from './pages/LoadPage'
import LoadSetupPage from './pages/LoadSetupPage'
import OwnerWalletPage from './pages/OwnerWalletPage'
import EWalletPage from './pages/EWalletPage'
import OwnerEWalletPage from './pages/OwnerEWalletPage'


function HomeRedirect() {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  return <Navigate to={user.role === 'OWNER' ? '/owner' : '/cashier'} replace />
}

export default function App() {
  const { user } = useAuth()
  return (
    <>
    {user && <IdleGuard />}
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/owner" element={<ProtectedRoute role="OWNER"><OwnerLayout /></ProtectedRoute>}>
        <Route path="wallet" element={<OwnerWalletPage key="load" kind="load" title="Load wallet" />} />
        <Route path="gcash-wallet" element={<OwnerWalletPage key="ewallet" kind="ewallet" title="GCash wallet" />} />
        <Route path="gcash" element={<OwnerEWalletPage />} />
      <Route path="wallet" element={<OwnerWalletPage />} />
      <Route path="load-setup" element={<LoadSetupPage />} />
      <Route path="customers" element={<OwnerCustomersPage />} />
        
        <Route path="shift-reports" element={<ShiftReportsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route index element={<OwnerHome />} />
        <Route path="products" element={<ProductsPage />} />
        <Route path="products/:id/units" element={<ProductUnitsPage />} />
        <Route path="restock" element={<RestockPage />} />
        <Route path="adjustments" element={<AdjustmentsPage />} />
        <Route path="stock-history" element={<StockHistoryPage />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="shifts" element={<ShiftsPage />} />
        
      </Route>

      <Route path="/cashier" element={<ProtectedRoute><CashierHome /></ProtectedRoute>} />
      <Route path="/gcash" element={<ProtectedRoute><EWalletPage /></ProtectedRoute>} />
      <Route path="/load" element={<ProtectedRoute><LoadPage /></ProtectedRoute>} />
      <Route path="/shift/start" element={<ProtectedRoute><StartShiftPage /></ProtectedRoute>} />
      <Route path="/price-check" element={<ProtectedRoute><PriceCheckPage /></ProtectedRoute>} />
      <Route path="/sales" element={<ProtectedRoute><SalesPage /></ProtectedRoute>} />
      <Route path="/receipts" element={<ProtectedRoute><ReceiptsPage /></ProtectedRoute>} />
      

      <Route path="/" element={<HomeRedirect />} />
      <Route path="*" element={<Navigate to="/" replace />} />
      <Route path="/shift/end" element={<ProtectedRoute><EndShiftPage /></ProtectedRoute>} />
      <Route path="/shift/summary" element={<ProtectedRoute><ShiftSummaryPage /></ProtectedRoute>} />
      <Route path="/reports/mine" element={<ProtectedRoute><MyReportsPage /></ProtectedRoute>} />
      <Route path="/customers" element={<ProtectedRoute><CustomersPage /></ProtectedRoute>} />
    </Routes>
    </>
  )
}