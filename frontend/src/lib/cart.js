// The cart. A guest's lives in this browser until checkout. A signed-in
// shopper's lives on the shop's server (shop/cart.py), so it is the same in
// every browser and support can change it when the shopper asks: what is here
// is a copy, changed at once on screen and corrected by the shop's answer.
// Prices here are for display: the shop works out what an order costs from its
// own catalogue.

import { useEffect, useState } from 'react'
import { api } from './api'
import { getSession, onSessionChange } from './auth'

const CART_KEY = 'ethnic-threads-cart-v1'
// The account's cart as last seen, so a reload does not start with an empty one.
const ACCOUNT_KEY = 'ethnic-threads-account-cart-v1'
// How often an open page asks the shop whether the cart changed elsewhere.
const REFRESH_MS = 5000
export const MAX_QUANTITY = 5
export const SIZES = ['S', 'M', 'L', 'XL', 'XXL', 'Free size']
const listeners = new Set()
const notify = () => listeners.forEach((listener) => listener())

const sameLine = (line, productId, size) => line.productId === productId && (line.size || null) === (size || null)

// ---- A guest's cart: this browser ----

function guestLines() {
  try {
    const lines = JSON.parse(localStorage.getItem(CART_KEY) || '[]')
    return Array.isArray(lines) ? lines.filter((line) => line && line.productId && line.quantity > 0) : []
  } catch {
    return []
  }
}

function saveGuest(lines) {
  try {
    localStorage.setItem(CART_KEY, JSON.stringify(lines))
  } catch {}
  notify()
  return lines
}

// ---- A shopper's cart: the shop's server ----

const shopperId = () => {
  const user = getSession()?.user
  return user?.role === 'shopper' ? user.id : null
}

let account = shopperId()
/** The shopper's cart as shown; null for a guest. */
let lines = account ? startingLines(account) : null
let error = ''
// Changes are sent one after another, and an answer is used only when none is
// still on its way: an older answer must not undo what was just clicked.
let chain = Promise.resolve()
let pending = 0
let changes = 0
let merging = false
let lastRead = 0

/** What to show until the shop answers: what this browser held as a guest, else the last cart seen. */
function startingLines(who) {
  const guest = guestLines()
  if (guest.length) return guest
  try {
    const kept = JSON.parse(localStorage.getItem(ACCOUNT_KEY) || 'null')
    return kept && kept.user === who && Array.isArray(kept.lines) ? kept.lines : []
  } catch {
    return []
  }
}

function show(next) {
  lines = next
  try {
    localStorage.setItem(ACCOUNT_KEY, JSON.stringify({ user: account, lines }))
  } catch {}
  notify()
  return lines
}

function setError(message) {
  if (error === message) return
  error = message
  notify()
}

/** Takes the shop's word for what the cart holds. Nothing happens when it is what is shown already. */
function accept(cart) {
  const next = (cart?.items || []).map((item) => ({
    productId: String(item.productId),
    title: item.title,
    brand: item.brand || null,
    imageUrl: item.imageUrl || null,
    price: Number(item.price) || 0,
    size: item.size || null,
    quantity: item.quantity,
    available: item.available !== false,
  }))
  if (JSON.stringify(next) !== JSON.stringify(lines)) show(next)
}

/** Sends one change to the shop, after the ones before it. `work` resolves to the shop's `{ cart }`. */
function send(work) {
  const who = account
  pending += 1
  changes += 1
  chain = chain.then(async () => {
    let cart = null
    let failure = ''
    try {
      cart = (await work()).cart
    } catch (err) {
      failure = err.message
    }
    pending -= 1
    // Signed out, or signed in as someone else, while this was on its way.
    if (account !== who) return
    setError(failure)
    if (pending) return
    if (cart) accept(cart)
    else await refresh(true)
  })
}

/** Reads the cart from the shop: this is how a change made elsewhere, or by support, shows up. */
async function refresh(force = false) {
  const who = account
  if (!who || pending || (!force && Date.now() - lastRead < 1000)) return
  lastRead = Date.now()
  const seen = changes
  try {
    const { cart } = await api('/cart')
    if (account === who && changes === seen) accept(cart)
  } catch {
    // What is on screen stays; the next read may work.
  }
}

/** Folds what this browser held as a guest into the account's cart, then shows the account's cart. */
function sync() {
  if (!account) return
  const guest = guestLines()
  if (!guest.length) {
    void refresh()
    return
  }
  if (merging) return
  merging = true
  send(async () => {
    try {
      const answer = await api('/cart/merge', { method: 'POST', body: { items: cartItems(guest) } })
      // The account holds them now.
      try {
        localStorage.removeItem(CART_KEY)
      } catch {}
      return answer
    } finally {
      merging = false
    }
  })
}

onSessionChange(() => {
  const who = shopperId()
  if (who === account) return
  account = who
  // An answer still on its way belongs to the cart that was shown before.
  changes += 1
  error = ''
  if (!who) {
    lines = null
    try {
      localStorage.removeItem(ACCOUNT_KEY)
    } catch {}
    notify()
    return
  }
  lines = startingLines(who)
  notify()
  sync()
})

const whenVisible = () => {
  if (document.visibilityState === 'visible') void refresh()
}
let watchers = 0
let timer = null

function watch() {
  watchers += 1
  if (watchers > 1) return
  timer = setInterval(whenVisible, REFRESH_MS)
  window.addEventListener('focus', whenVisible)
  document.addEventListener('visibilitychange', whenVisible)
}

function unwatch() {
  watchers -= 1
  if (watchers > 0) return
  clearInterval(timer)
  window.removeEventListener('focus', whenVisible)
  document.removeEventListener('visibilitychange', whenVisible)
}

// ---- What the pages use ----

export function getCart() {
  return account ? lines : guestLines()
}

/** Shows the cart with one line changed, and tells the shop when the cart is the account's. */
function put(next, productId, size, quantity) {
  if (!account) return saveGuest(next)
  setError('')
  show(next)
  send(() => api('/cart/items', { method: 'PUT', body: { productId, size: size || null, quantity } }))
  return next
}

/** Adds a product (or more of it). The same product in another size is another line. */
export function addToCart(product, { size = null, quantity = 1 } = {}) {
  const current = getCart()
  const productId = String(product.id)
  const existing = current.find((line) => sameLine(line, productId, size))
  const total = Math.max(1, Math.min(MAX_QUANTITY, (existing?.quantity || 0) + quantity))
  if (existing) {
    return put(
      current.map((line) => (line === existing ? { ...line, quantity: total } : line)),
      productId,
      size,
      total
    )
  }
  return put(
    [
      ...current,
      {
        productId,
        title: product.title,
        brand: product.brand || null,
        imageUrl: product.image_url || product.imageUrl || null,
        price: Number(product.price_current ?? product.price) || 0,
        size: size || null,
        quantity: total,
      },
    ],
    productId,
    size,
    total
  )
}

export function setQuantity(productId, size, quantity) {
  const current = getCart()
  if (quantity < 1) {
    return put(
      current.filter((line) => !sameLine(line, productId, size)),
      productId,
      size,
      0
    )
  }
  const total = Math.min(MAX_QUANTITY, quantity)
  return put(
    current.map((line) => (sameLine(line, productId, size) ? { ...line, quantity: total } : line)),
    productId,
    size,
    total
  )
}

export const removeFromCart = (productId, size) => setQuantity(productId, size, 0)

/** After an order. The shop empties an account's cart itself when the order is placed. */
export function clearCart() {
  if (!account) return saveGuest([])
  changes += 1
  return show([])
}

export const cartCount = (lines = getCart()) => lines.reduce((sum, line) => sum + line.quantity, 0)
export const cartSubtotal = (lines = getCart()) =>
  Math.round(lines.reduce((sum, line) => sum + line.price * line.quantity, 0) * 100) / 100

/** What checkout sends: ids, sizes and quantities, nothing the shopper could have edited a price in. */
export const cartItems = (lines = getCart()) =>
  lines.map((line) => ({ productId: line.productId, quantity: line.quantity, size: line.size }))

/** The cart's lines, kept current. While a page shows them, a shopper's cart is re-read from the shop. */
export function useCart() {
  const [current, setCurrent] = useState(getCart)
  useEffect(() => {
    const update = () => setCurrent(getCart())
    listeners.add(update)
    watch()
    sync()
    return () => {
      listeners.delete(update)
      unwatch()
    }
  }, [])
  return current
}

/** Why the shop refused the last change to the cart ('' when it did not). */
export function useCartError() {
  const [message, setMessage] = useState(error)
  useEffect(() => {
    const update = () => setMessage(error)
    listeners.add(update)
    update()
    return () => listeners.delete(update)
  }, [])
  return message
}

const RUPEE = '₹'
export const rupees = (amount) =>
  `${RUPEE}${Number(amount || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
