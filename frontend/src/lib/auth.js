// Who is signed in. The shop's server issues the session; this keeps it in the browser.

import { useEffect, useState } from 'react'

const SESSION_KEY = 'ethnic-threads-session-v1'
const listeners = new Set()

export function getSession() {
  try {
    const session = JSON.parse(localStorage.getItem(SESSION_KEY) || 'null')
    return session && session.token && session.user ? session : null
  } catch {
    return null
  }
}

function changed() {
  listeners.forEach((listener) => listener())
}

export function setSession(token, user) {
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify({ token, user }))
  } catch {}
  changed()
}

export function clearSession() {
  try {
    localStorage.removeItem(SESSION_KEY)
  } catch {}
  changed()
}

export function onSessionChange(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** The signed-in user ({ id, role, name, email }) or null, kept current as people sign in and out. */
export function useUser() {
  const [user, setUser] = useState(() => getSession()?.user ?? null)
  useEffect(() => onSessionChange(() => setUser(getSession()?.user ?? null)), [])
  return user
}

export const isAdmin = (user) => user?.role === 'admin'
export const isShopper = (user) => user?.role === 'shopper'
