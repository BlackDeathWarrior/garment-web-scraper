// The storefront's side of the support desk integration.
//
// The browser never talks to the support desk's API and never holds a key:
// it asks our own worker (/api/support/*), which does. A shopper reads a
// request back with the tracking token the worker returned when it was made;
// those are kept here, in this browser.

const REQUESTS_KEY = 'ethnic-threads-requests-v1'
const MAX_SAVED = 30

export class SupportError extends Error {
  constructor(message, status, reason) {
    super(message)
    this.name = 'SupportError'
    this.status = status
    this.reason = reason
  }
}

const apiBase = () => import.meta.env.VITE_API_BASE || ''

/** The admin's session from /api/auth/login; registered shoppers have none. */
export function adminSession() {
  if (localStorage.getItem('scraper_user_role') !== 'admin') return null
  return localStorage.getItem('scraper_auth_token')
}

async function api(path, { method = 'GET', body, token } = {}) {
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers['X-Request-Token'] = token
  const session = adminSession()
  if (session) headers.Authorization = `Bearer ${session}`

  let response
  try {
    response = await fetch(`${apiBase()}/api/support${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new SupportError('Connection error. Please check your internet and try again.', 0, 'network')
  }
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new SupportError(
      data.message || 'Something went wrong. Please try again.',
      response.status,
      data.reason
    )
  }
  return data
}

let configPromise = null

/** What is switched on. Never rejects: with no worker, everything is off. */
export function getSupportConfig() {
  if (!configPromise) {
    configPromise = api('/config').catch(() => ({ tickets: false, widget: null, issues: [] }))
  }
  return configPromise
}

export function resetSupportConfig() {
  configPromise = null
}

/** A new id per form: a retry of the same submission creates nothing new. */
export function newRequestId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `r-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}

/** Who is using this browser, as far as the storefront knows. Unverified. */
export function currentVisitor() {
  try {
    const user = JSON.parse(localStorage.getItem('scraper_current_user') || 'null')
    if (user && typeof user === 'object') {
      return { name: String(user.username || ''), email: String(user.email || '') }
    }
  } catch {}
  return { name: '', email: '' }
}

// ---- Requests this browser has made ----

export function savedRequests() {
  try {
    const list = JSON.parse(localStorage.getItem(REQUESTS_KEY) || '[]')
    return Array.isArray(list) ? list.filter((r) => r && r.reference && r.token) : []
  } catch {
    return []
  }
}

export function saveRequest(entry) {
  const rest = savedRequests().filter((r) => r.reference !== entry.reference)
  const next = [{ ...entry, savedAt: new Date().toISOString() }, ...rest].slice(0, MAX_SAVED)
  try {
    localStorage.setItem(REQUESTS_KEY, JSON.stringify(next))
  } catch {}
  return next
}

export function tokenFor(reference) {
  const wanted = String(reference).toUpperCase()
  return savedRequests().find((r) => r.reference.toUpperCase() === wanted)?.token || null
}

/** Whether this browser has already rated a request. */
export function isRated(reference) {
  const wanted = String(reference).toUpperCase()
  return Boolean(savedRequests().find((r) => r.reference.toUpperCase() === wanted)?.rated)
}

/** The link to a request's page. The token rides in the fragment, which is never sent to a server. */
export function requestLink(reference, token) {
  return `/requests/${encodeURIComponent(reference)}${token ? `#${token}` : ''}`
}

// ---- Calls ----

export async function createRequest(form) {
  const made = await api('/tickets', { method: 'POST', body: form })
  if (made.token) {
    saveRequest({ reference: made.reference, token: made.token, subject: form.subject || form.message })
  }
  return made
}

export const readRequest = (reference, token) =>
  api(`/requests/${encodeURIComponent(reference)}`, { token })

export const requestChanges = (reference, token) =>
  api(`/requests/${encodeURIComponent(reference)}/changes`, { token })

export const replyToRequest = (reference, token, message, requestId) =>
  api(`/requests/${encodeURIComponent(reference)}/messages`, {
    method: 'POST',
    token,
    body: { message, requestId },
  })

export const rateRequest = (reference, token, rating, comment) =>
  api(`/requests/${encodeURIComponent(reference)}/rating`, {
    method: 'POST',
    token,
    body: { rating, comment },
  })

export const adminOverview = () => api('/admin/overview')

export const chatIdentity = () => api('/identity')

// ---- What the visitor is looking at, for the chat widget ----

let pageContext = {}
const listeners = new Set()

export function setSupportContext(context) {
  pageContext = context || {}
  listeners.forEach((listener) => listener(pageContext))
}

export function getSupportContext() {
  return pageContext
}

export function onSupportContext(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** The few facts about a listing worth telling support. */
export function productContext(product) {
  if (!product) return {}
  const context = {
    product_id: product.id,
    title: product.title,
    source: product.source,
    price_current: product.price_current,
  }
  return Object.fromEntries(Object.entries(context).filter(([, value]) => value != null))
}

export function formatWhen(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}
