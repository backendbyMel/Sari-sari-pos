import { apiFetch } from './api'
import { flattenErrors } from './utils'

export async function downloadFile(path, filename) {
  const response = await apiFetch(path)
  if (!response.ok) {
    let message = 'Could not create the file. Please try again.'
    if (response.status === 400) {
      try {
        message = flattenErrors(await response.json()).join(' ')
      } catch {
        // keep the general message
      }
    }
    throw new Error(message)
  }
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename  
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10000)   
}