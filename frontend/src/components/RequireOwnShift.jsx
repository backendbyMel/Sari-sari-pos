import { Link } from 'react-router-dom'
import { useCurrentShift } from '../useCurrentShift'

export default function RequireOwnShift({ title, children }) {
  const { loading, error, shift, isMine } = useCurrentShift()
  if (loading) return <p style={{ padding: 24, fontFamily: 'sans-serif' }}>Loading...</p>
  if (error) return <p style={{ padding: 24, fontFamily: 'sans-serif', color: 'crimson' }}>{error}</p>
  if (!shift || !isMine) {
    return (
      <div style={{ maxWidth: 520, margin: '0 auto', padding: 16, fontFamily: 'sans-serif' }}>
        <p><Link to="/">&larr; Back</Link></p>
        <h1>{title}</h1>
        <p style={{ background: '#fdecea', padding: 14, borderRadius: 8 }}>
          You need your own open shift for this. <Link to="/shift/start"><b>Start shift</b></Link>
        </p>
      </div>
    )
  }
  return children
}