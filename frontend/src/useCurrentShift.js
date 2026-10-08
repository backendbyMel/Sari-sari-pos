import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from './api'

export function useCurrentShift() {
  const [state, setState] = useState({ loading: true, error: '', shift: null, isMine: false })

  const reload = useCallback(async () => {
    try {
      const response = await apiFetch('/shifts/current/')
      if (response.ok) {
        const data = await response.json()
        setState({ loading: false, error: '', shift: data.shift, isMine: data.is_mine })
      } else if (response.status !== 401) {
        setState((s) => ({ ...s, loading: false, error: 'Could not check the shift. Please try again.' }))
      }
    } catch {
      setState((s) => ({ ...s, loading: false, error: 'Cannot reach the server. Is Django running?' }))
    }
  }, [])

  useEffect(() => { reload() }, [reload])

  return { ...state, reload }
}