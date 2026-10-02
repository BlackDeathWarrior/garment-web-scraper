import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { FiMinus, FiPlus, FiShoppingCart, FiTrash2 } from 'react-icons/fi'
import Navbar from '../components/Navbar'
import { api } from '../lib/api'
import { useUser } from '../lib/auth'
import { cartCount, cartItems, MAX_QUANTITY, removeFromCart, rupees, setQuantity, useCart } from '../lib/cart'

export default function Cart() {
  const lines = useCart()
  const user = useUser()
  const navigate = useNavigate()
  const [quote, setQuote] = useState(null)
  const [error, setError] = useState('')

  // The shop prices the cart: what is shown at checkout is what will be charged.
  useEffect(() => {
    if (!lines.length) {
      setQuote(null)
      return undefined
    }
    let active = true
    api('/checkout/quote', { method: 'POST', body: { items: cartItems(lines) } })
      .then((priced) => {
        if (active) {
          setQuote(priced)
          setError('')
        }
      })
      .catch((err) => active && setError(err.message))
    return () => {
      active = false
    }
  }, [lines])

  const checkout = () => navigate(user ? '/checkout' : '/login?next=/checkout')

  return (
    <div className="min-h-screen bg-[#faf8f5]">
      <Navbar />
      <div className="max-w-5xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold text-gray-900 tracking-tight mb-6">Your Cart</h1>

        {lines.length === 0 ? (
          <div className="bg-white rounded-3xl border border-gray-100 p-10 text-center">
            <FiShoppingCart className="mx-auto text-gray-300 mb-4" size={36} />
            <p className="text-gray-600 mb-4">Your cart is empty.</p>
            <Link to="/" className="text-maroon-700 font-bold hover:underline">
              Continue shopping
            </Link>
          </div>
        ) : (
          <div className="grid lg:grid-cols-3 gap-6 items-start">
            <ul className="lg:col-span-2 space-y-3" aria-label="Cart items">
              {lines.map((line) => (
                <li
                  key={`${line.productId}-${line.size}`}
                  className="bg-white rounded-2xl border border-gray-100 p-4 flex gap-4"
                >
                  <img
                    src={line.imageUrl}
                    alt=""
                    className="w-20 h-24 object-cover rounded-xl bg-amber-50 shrink-0"
                  />
                  <div className="min-w-0 flex-1">
                    {line.brand && (
                      <p className="text-[10px] font-bold text-maroon-800 uppercase tracking-widest">{line.brand}</p>
                    )}
                    <p className="font-semibold text-gray-900 line-clamp-2">{line.title}</p>
                    {line.size && <p className="text-xs text-gray-500 mt-0.5">Size: {line.size}</p>}
                    <div className="flex flex-wrap items-center justify-between gap-3 mt-3">
                      <div className="flex items-center gap-1 bg-gray-50 border border-gray-200 rounded-xl p-1">
                        <button
                          aria-label={`One fewer ${line.title}`}
                          onClick={() => setQuantity(line.productId, line.size, line.quantity - 1)}
                          className="p-1.5 rounded-lg hover:bg-white"
                        >
                          <FiMinus size={14} />
                        </button>
                        <span className="w-6 text-center text-sm font-bold" aria-label="Quantity">
                          {line.quantity}
                        </span>
                        <button
                          aria-label={`One more ${line.title}`}
                          disabled={line.quantity >= MAX_QUANTITY}
                          onClick={() => setQuantity(line.productId, line.size, line.quantity + 1)}
                          className="p-1.5 rounded-lg hover:bg-white disabled:opacity-30"
                        >
                          <FiPlus size={14} />
                        </button>
                      </div>
                      <p className="font-bold text-gray-900">{rupees(line.price * line.quantity)}</p>
                      <button
                        onClick={() => removeFromCart(line.productId, line.size)}
                        aria-label={`Remove ${line.title}`}
                        className="text-gray-400 hover:text-maroon-700 flex items-center gap-1 text-xs font-bold"
                      >
                        <FiTrash2 size={14} /> Remove
                      </button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>

            <aside className="bg-white rounded-2xl border border-gray-100 p-5 space-y-3" aria-label="Order summary">
              <h2 className="text-sm font-bold text-gray-400 uppercase tracking-widest">Summary</h2>
              {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
              <Row label={`Items (${cartCount(lines)})`} value={quote ? rupees(quote.subtotal) : '...'} />
              <Row
                label="Delivery"
                value={quote ? (quote.shippingFee ? rupees(quote.shippingFee) : 'Free') : '...'}
              />
              <div className="border-t border-gray-100 pt-3">
                <Row label="Total" value={quote ? rupees(quote.total) : '...'} strong />
              </div>
              <button
                onClick={checkout}
                disabled={!quote}
                className="w-full bg-maroon-700 hover:bg-maroon-800 text-white font-bold py-3.5 rounded-xl transition-all shadow-lg shadow-maroon-900/20 disabled:opacity-50"
              >
                Proceed to checkout
              </button>
              {!user && <p className="text-xs text-gray-500 text-center">You will be asked to sign in first.</p>}
            </aside>
          </div>
        )}
      </div>
    </div>
  )
}

export function Row({ label, value, strong }) {
  return (
    <div className={`flex items-center justify-between text-sm ${strong ? 'font-bold text-gray-900 text-base' : 'text-gray-600'}`}>
      <span>{label}</span>
      <span>{value}</span>
    </div>
  )
}
