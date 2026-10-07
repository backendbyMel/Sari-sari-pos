import { useState } from 'react'
import { API_URL } from './api'

function App() {
  const [result, setResult] = useState('Not tested yet.')

  async function testConnection() {
    setResult('Calling Django...')
    try {
      const response = await fetch(`${API_URL}/auth/me/`)
      setResult(`Django answered with status ${response.status}.`)
    } catch (error) {
      setResult(`Could not reach Django: ${error.message}`)
    }
  }

  return (
    <div style={{ padding: 24, fontFamily: 'sans-serif' }}>
      <h1>Sari-Sari Store POS</h1>
      <button onClick={testConnection}>Test connection to Django</button>
      <p>{result}</p>
    </div>
  )
}

export default App