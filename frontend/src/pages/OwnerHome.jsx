import { Link } from 'react-router-dom'
import { useAuth } from '../AuthContext'

export default function OwnerHome() {
  const { user } = useAuth()
  return (
    <div>
      <h1>Owner Home</h1>
      <p>Welcome, <b>{user.username}</b>. The dashboard comes in Phase 4.</p>
      <p><Link to="/owner/products">Manage products</Link></p>
    </div>
  )
}