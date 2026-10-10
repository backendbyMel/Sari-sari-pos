import { useEffect, useRef, useState } from 'react'
import { apiFetch } from './api'
import { useAuth } from './AuthContext'

const DEFAULT_MINUTES = 15
const ACTIVITY = ['mousedown', 'mousemove', 'keydown', 'touchstart', 'wheel']
const NOTICE_KEY = 'pos_notice'

export default function IdleGuard() {
  const { logout } = useAuth()
  const [minutes, setMinutes] = useState(DEFAULT_MINUTES)
  const [secondsLeft, setSecondsLeft] = useState(null)   // null = no warning showing
  const lastActivity = useRef(Date.now())
  const warning = useRef(false)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const response = await apiFetch('/settings/public/')
        if (response.ok && !cancelled) {
          const data = await response.json()
          setMinutes(Number(data.idle_logout_minutes) || DEFAULT_MINUTES)
        }
      } catch {
        // keep the default
      }
    }
    load()
    window.addEventListener('settings-changed', load)
    return () => {
      cancelled = true
      window.removeEventListener('settings-changed', load)
    }
  }, [])

  useEffect(() => {
    lastActivity.current = Date.now()
    warning.current = false
    setSecondsLeft(null)

    const totalMs = minutes * 60 * 1000
    const warnMs = Math.min(60 * 1000, totalMs / 3)

    function onActivity(event) {
      if (warning.current && event.type === 'mousemove') return
      lastActivity.current = Date.now()
      if (warning.current) {
        warning.current = false
        setSecondsLeft(null)
      }
    }
    ACTIVITY.forEach((name) => window.addEventListener(name, onActivity, { passive: true }))

    const timer = setInterval(() => {
      const idle = Date.now() - lastActivity.current
      if (idle >= totalMs) {
        clearInterval(timer)
        sessionStorage.setItem(
          NOTICE_KEY,
          'You were logged out because of inactivity. Your shift is still open.'
        )
        logout()
      } else if (idle >= totalMs - warnMs) {
        warning.current = true
        setSecondsLeft(Math.ceil((totalMs - idle) / 1000))
      }
    }, 1000)

    return () => {
      clearInterval(timer)
      ACTIVITY.forEach((name) => window.removeEventListener(name, onActivity))
    }
  }, [minutes, logout])

  if (secondsLeft === null) return null

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div style={{ background: '#fff', borderRadius: 8, padding: 24, maxWidth: 380, fontFamily: 'sans-serif', textAlign: 'center' }}>
        <h2 style={{ marginTop: 0 }}>Are you still there?</h2>
        <p style={{ fontSize: 18 }}>
          You will be logged out in <b>{secondsLeft}</b> seconds.
        </p>
        <p style={{ color: '#555' }}>
          Your shift stays open, but an unfinished <b>held sale</b> on the screen will be lost.
        </p>
        <button autoFocus style={{ padding: '12px 24px', fontSize: 18 }}>
          Stay logged in
        </button>
      </div>
    </div>
  )
}