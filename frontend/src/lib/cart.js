// The cart lives in this browser until checkout. Prices here are for display:
// the shop works out what an order costs from its own catalogue.

import { useEffect, useState } from 'react'

const CART_KEY = 'ethnic-threads-cart-v1'
export const MAX_QUANTITY = 5
export const SIZES = ['S', 'M', 'L', 'XL', 'XXL', 'Free size']
const listeners = new Set()

export function getCart() {
  try {
    const lines = JSON.parse(localStorage.getItem(CART_KEY) || '[]')
    return Array.isArray(lines) ? lines.filter((line) => line && line.productId && line.quantity > 0) : []
  } catch {
    return []
  }
}

function save(lines) {
  try {
    localStorage.setItem(CART_KEY, JSON.stringify(lines))
  } catch {}
  listeners.forEach((listener) => listener())
  return lines
}

const sameLine = (line, productId, size) => line.productId === productId && (line.size || null) === (size || null)

/** Adds a product (or more of it). The same product in another size is another line. */
export function addToCart(product, { size = null, quantity = 1 } = {}) {
  const lines = getCart()
  const existing = lines.find((line) => sameLine(line, String(product.id), size))
  if (existing) {
    existing.quantity = Math.min(MAX_QUANTITY, existing.quantity + quantity)
    return save(lines)
  }
  return save([
    ...lines,
    {
      productId: String(product.id),
      title: product.title,
      brand: product.brand || null,
      imageUrl: product.image_url || product.imageUrl || null,
      price: Number(product.price_current ?? product.price) || 0,
      size: size || null,
      quantity: Math.max(1, Math.min(MAX_QUANTITY, quantity)),
    },
  ])
}

export function setQuantity(productId, size, quantity) {
  const lines = getCart()
  if (quantity < 1) return save(lines.filter((line) => !sameLine(line, productId, size)))
  return save(
    lines.map((line) =>
      sameLine(line, productId, size) ? { ...line, quantity: Math.min(MAX_QUANTITY, quantity) } : line
    )
  )
}

export const removeFromCart = (productId, size) => setQuantity(productId, size, 0)
export const clearCart = () => save([])

export const cartCount = (lines = getCart()) => lines.reduce((sum, line) => sum + line.quantity, 0)
export const cartSubtotal = (lines = getCart()) =>
  Math.round(lines.reduce((sum, line) => sum + line.price * line.quantity, 0) * 100) / 100

/** What checkout sends: ids, sizes and quantities, nothing the shopper could have edited a price in. */
export const cartItems = (lines = getCart()) =>
  lines.map((line) => ({ productId: line.productId, quantity: line.quantity, size: line.size }))

export function useCart() {
  const [lines, setLines] = useState(getCart)
  useEffect(() => {
    const update = () => setLines(getCart())
    listeners.add(update)
    return () => listeners.delete(update)
  }, [])
  return lines
}

const RUPEE = '₹'
export const rupees = (amount) =>
  `${RUPEE}${Number(amount || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
