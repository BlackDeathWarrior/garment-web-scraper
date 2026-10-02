// Calls to the shop's API (shop/server.py), with the signed-in session attached.

import { getSession } from './auth'

export class ApiError extends Error {
  constructor(message, status, reason) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.reason = reason
  }
}

export const apiBase = () => import.meta.env.VITE_API_BASE || ''

export async function api(path, { method = 'GET', body, headers = {} } = {}) {
  const all = { ...headers }
  if (body !== undefined) all['Content-Type'] = 'application/json'
  const session = getSession()
  if (session?.token) all.Authorization = `Bearer ${session.token}`

  let response
  try {
    response = await fetch(`${apiBase()}/api${path}`, {
      method,
      headers: all,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError('Connection error. Please check your internet and try again.', 0, 'network')
  }
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new ApiError(data.message || 'Something went wrong. Please try again.', response.status, data.reason)
  }
  return data
}
