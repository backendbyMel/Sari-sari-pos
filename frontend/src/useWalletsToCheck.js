import { useEffect, useState } from 'react'
import { apiFetch } from './api'

export function useWalletsToCheck(shiftId) {
  const [state, setState] = useState({ wallets: null, error: '' })

  useEffect(() => {
    let cancelled = false
    async function load() {
      const query = shiftId ? `?shift=${shiftId}` : ''
      try {
        const response = await apiFetch(`/shifts/wallets-to-check/${query}`)
        if (cancelled) return
        if (response.ok) setState({ wallets: (await response.json()).wallets, error: '' })
        else if (response.status !== 401) setState({ wallets: null, error: 'Could not check which wallets to count.' })
      } catch {
        if (!cancelled) setState({ wallets: null, error: 'Cannot reach the server. Is Django running?' })
      }
    }
    load()
    return () => { cancelled = true }
  }, [shiftId])

  return state
}