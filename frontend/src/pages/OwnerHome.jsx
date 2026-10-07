import { useState } from 'react'
import { apiFetch } from '../api'
import { useAuth } from '../AuthContext'

export default function OwnerHome() {
  const { user, logout } = useAuth()
  const [message, setMessage] = useState('')

  async function testOwnerEndpoint() {
    const response = await apiFetch('/auth/owner-check/')
    setMessage(`Owner-only endpoint answered with status ${response.status}.`)
  }

  return (
    <div style={{ padding: 24, fontFamily: 'sans-serif' }}>
      <h1>Owner Home</h1>
      <p>Logged in as <b>{user.username}</b> ({user.role})</p>
      <button onClick={testOwnerEndpoint}>Test an Owner-only endpoint</button>{' '}
      <button onClick={logout}>Log out</button>
      <p>{message}</p>
    </div>
  )
}