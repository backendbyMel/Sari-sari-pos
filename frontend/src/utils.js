export const PESO = '\u20B1'   // the peso sign

export const toCents = (value) => Math.round(parseFloat(value) * 100)

export const peso = (cents) =>
  PESO + (cents / 100).toLocaleString('en-PH', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })

export function flattenErrors(data) {
  if (typeof data === 'string') return [data]
  if (Array.isArray(data)) return data.flatMap(flattenErrors)
  if (data && typeof data === 'object') return Object.values(data).flatMap(flattenErrors)
  return []
}

export const formatTime = (iso) =>
  iso
    ? new Date(iso).toLocaleString('en-PH', { timeZone: 'Asia/Manila', dateStyle: 'medium', timeStyle: 'short' })
    : ''

export const signedPeso = (cents) =>
  (cents < 0 ? '-' : cents > 0 ? '+' : '') + peso(Math.abs(cents))