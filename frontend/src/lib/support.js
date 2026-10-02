// The storefront's side of the support desk integration.
//
// The browser never talks to the support desk's API and never holds a key:
// it asks the shop (/api/support/*), which does. A signed-in shopper's
// requests are found under their account. A guest reads the one request they
// sent with the tracking token in its link, which is kept in this browser.

import { api, ApiError } from './api'
import { getSession } from './auth'

export { ApiError as SupportError }

const REQUESTS_KEY = 'ethnic-threads-requests-v1'
const MAX_SAVED = 30

let configPromise = null

/**
 * What is switched on. Never rejects: with no shop server, everything is off.
 * Only a real answer is remembered. A failed call (the shop server restarting,
 * a dropped connection) is asked again next time, instead of leaving the chat
 * and every form switched off until the page is reloaded.
 */
export function getSupportConfig() {
  if (!configPromise) {
    const asked = api('/support/config').catch(() => {
      if (configPromise === asked) configPromise = null
      return { tickets: false, widget: null, issues: [], topics: [], failed: true }
    })
    configPromise = asked
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

/** Who is using this browser, for prefilling forms and the chat. */
export function currentVisitor() {
  const user = getSession()?.user
  return { name: user?.name || '', email: user?.email || '' }
}

// ---- Requests a guest made in this browser ----

export function savedRequests() {
  try {
    const list = JSON.parse(localStorage.getItem(REQUESTS_KEY) || '[]')
    return Array.isArray(list) ? list.filter((r) => r && r.reference) : []
  } catch {
    return []
  }
}

export function saveRequest(entry) {
  const known = savedRequests().find((r) => r.reference === entry.reference) || {}
  const rest = savedRequests().filter((r) => r.reference !== entry.reference)
  const next = [{ ...known, ...entry, savedAt: known.savedAt || new Date().toISOString() }, ...rest].slice(0, MAX_SAVED)
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

/** The link to a request's page. A guest's token rides in the fragment, which is never sent to a server. */
export function requestLink(reference, token) {
  return `/requests/${encodeURIComponent(reference)}${token ? `#${token}` : ''}`
}

// ---- Calls ----

const withToken = (token) => (token ? { 'X-Request-Token': token } : {})

export async function createRequest(form) {
  const made = await api('/support/tickets', { method: 'POST', body: form })
  if (made.token) {
    saveRequest({ reference: made.reference, token: made.token, subject: form.subject || form.message })
  }
  return made
}

/** The signed-in shopper's requests, as the support desk has them. */
export const myRequests = () => api('/support/requests').then((r) => r.requests)

export const readRequest = (reference, token) =>
  api(`/support/requests/${encodeURIComponent(reference)}`, { headers: withToken(token) })

export const requestChanges = (reference, token) =>
  api(`/support/requests/${encodeURIComponent(reference)}/changes`, { headers: withToken(token) })

export const replyToRequest = (reference, token, message, requestId) =>
  api(`/support/requests/${encodeURIComponent(reference)}/messages`, {
    method: 'POST',
    headers: withToken(token),
    body: { message, requestId },
  })

export const rateRequest = (reference, token, rating, comment) =>
  api(`/support/requests/${encodeURIComponent(reference)}/rating`, {
    method: 'POST',
    headers: withToken(token),
    body: { rating, comment },
  })

export const adminOverview = () => api('/support/admin/overview')

export const chatIdentity = () => api('/support/identity')

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

/** The few facts about a product worth telling support. */
export function productContext(product) {
  if (!product) return {}
  const context = {
    product_id: product.id,
    title: product.title,
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

export function formatDay(iso) {
  if (!iso) return ''
  const date = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })
}
