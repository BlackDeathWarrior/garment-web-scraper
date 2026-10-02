import { useEffect, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { FiLock } from 'react-icons/fi'
import Navbar from '../components/Navbar'
import { Row } from './Cart'
import { api } from '../lib/api'
import { isShopper, useUser } from '../lib/auth'
import { cartItems, clearCart, rupees, useCart } from '../lib/cart'

const EMPTY_ADDRESS = { name: '', phone: '', line1: '', line2: '', city: '', state: '', pincode: '' }

/** Address, delivery, payment, place the order. No card or UPI details are asked for: payment is simulated. */
export default function Checkout() {
  const user = useUser()
  const lines = useCart()
  const navigate = useNavigate()
  const [options, setOptions] = useState(null)
  const [saved, setSaved] = useState([])
  const [chosen, setChosen] = useState('new')
  const [address, setAddress] = useState(EMPTY_ADDRESS)
  const [delivery, setDelivery] = useState('standard')
  const [payment, setPayment] = useState('cod')
  const [quote, setQuote] = useState(null)
  const [error, setError] = useState('')
  const [placing, setPlacing] = useState(false)

  useEffect(() => {
    if (!isShopper(user)) return
    api('/checkout/options').then(setOptions).catch((err) => setError(err.message))
    api('/addresses')
      .then(({ addresses }) => {
        setSaved(addresses)
        if (addresses.length) setChosen(addresses[0].id)
        else setAddress((a) => ({ ...a, name: user.name }))
      })
      .catch(() => {})
  }, [user])

  useEffect(() => {
    if (!lines.length) return undefined
    let active = true
    api('/checkout/quote', { method: 'POST', body: { items: cartItems(lines), delivery } })
      .then((priced) => active && setQuote(priced))
      .catch((err) => active && setError(err.message))
    return () => {
      active = false
    }
  }, [lines, delivery])

  if (!user) return <Navigate to="/login?next=/checkout" replace />
  if (!isShopper(user)) return <Navigate to="/admin" replace />
  if (!lines.length && !placing) return <Navigate to="/cart" replace />

  const place = async (e) => {
    e.preventDefault()
    setError('')
    setPlacing(true)
    try {
      const deliverTo = chosen === 'new' ? address : saved.find((a) => a.id === chosen)
      const { order } = await api('/orders', {
        method: 'POST',
        body: { items: cartItems(lines), address: deliverTo, delivery, payment, saveAddress: chosen === 'new' },
      })
      clearCart()
      navigate(`/orders/${order.id}?placed=1`)
    } catch (err) {
      setError(err.message)
      setPlacing(false)
    }
  }

  const set = (key) => (e) => setAddress({ ...address, [key]: e.target.value })
  const field =
    'w-full px-3 py-2.5 rounded-xl border border-gray-200 focus:ring-2 focus:ring-maroon-500 outline-none bg-gray-50 text-sm'
  const card = 'bg-white rounded-2xl border border-gray-100 p-5'
  const heading = 'text-sm font-bold text-gray-400 uppercase tracking-widest mb-4'

  return (
    <div className="min-h-screen bg-[#faf8f5]">
      <Navbar />
      <form onSubmit={place} className="max-w-5xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold text-gray-900 tracking-tight mb-6">Checkout</h1>
        <div className="grid lg:grid-cols-3 gap-6 items-start">
          <div className="lg:col-span-2 space-y-5">
            <section className={card} aria-label="Delivery address">
              <h2 className={heading}>1. Delivery address</h2>
              {saved.map((a) => (
                <label key={a.id} className="flex items-start gap-3 mb-3 cursor-pointer">
                  <input type="radio" name="address" checked={chosen === a.id} onChange={() => setChosen(a.id)} className="mt-1" />
                  <span className="text-sm text-gray-700">
                    <span className="font-semibold text-gray-900">{a.name}</span>, {a.line1}
                    {a.line2 ? `, ${a.line2}` : ''}, {a.city}, {a.state} {a.pincode} · {a.phone}
                  </span>
                </label>
              ))}
              {saved.length > 0 && (
                <label className="flex items-center gap-3 mb-3 cursor-pointer">
                  <input type="radio" name="address" checked={chosen === 'new'} onChange={() => setChosen('new')} />
                  <span className="text-sm font-semibold text-gray-900">A new address</span>
                </label>
              )}
              {chosen === 'new' && (
                <div className="grid sm:grid-cols-2 gap-3">
                  <input aria-label="Full name" placeholder="Full name" required value={address.name} onChange={set('name')} className={field} />
                  <input aria-label="Phone number" placeholder="Phone number" required inputMode="tel" value={address.phone} onChange={set('phone')} className={field} />
                  <input aria-label="Address line 1" placeholder="House, street" required value={address.line1} onChange={set('line1')} className={`${field} sm:col-span-2`} />
                  <input aria-label="Address line 2" placeholder="Area, landmark (optional)" value={address.line2} onChange={set('line2')} className={`${field} sm:col-span-2`} />
                  <input aria-label="City" placeholder="City" required value={address.city} onChange={set('city')} className={field} />
                  <input aria-label="State" placeholder="State" required value={address.state} onChange={set('state')} className={field} />
                  <input aria-label="PIN code" placeholder="PIN code" required inputMode="numeric" maxLength={6} value={address.pincode} onChange={set('pincode')} className={field} />
                </div>
              )}
            </section>

            <section className={card} aria-label="Delivery option">
              <h2 className={heading}>2. Delivery</h2>
              {(options?.delivery || []).map((option) => (
                <label key={option.key} className="flex items-center gap-3 mb-2 cursor-pointer">
                  <input type="radio" name="delivery" checked={delivery === option.key} onChange={() => setDelivery(option.key)} />
                  <span className="text-sm text-gray-700">
                    <span className="font-semibold text-gray-900">{option.label}</span> · about {option.days} days ·{' '}
                    {option.freeOver ? `${rupees(option.fee)}, free over ${rupees(option.freeOver)}` : rupees(option.fee)}
                  </span>
                </label>
              ))}
            </section>

            <section className={card} aria-label="Payment">
              <h2 className={heading}>3. Payment</h2>
              {(options?.payments || []).map((method) => (
                <label key={method.key} className="flex items-center gap-3 mb-2 cursor-pointer">
                  <input type="radio" name="payment" checked={payment === method.key} onChange={() => setPayment(method.key)} />
                  <span className="text-sm font-semibold text-gray-900">{method.label}</span>
                </label>
              ))}
              <p className="text-xs text-gray-500 mt-3 flex items-start gap-2">
                <FiLock className="mt-0.5 shrink-0" />
                This is a demonstration shop. No card or UPI details are asked for and no money is taken: paying is simulated.
              </p>
            </section>
          </div>

          <aside className={`${card} space-y-3`} aria-label="Order summary">
            <h2 className="text-sm font-bold text-gray-400 uppercase tracking-widest">Order summary</h2>
            <ul className="space-y-2 max-h-56 overflow-y-auto">
              {lines.map((line) => (
                <li key={`${line.productId}-${line.size}`} className="flex justify-between gap-3 text-sm text-gray-700">
                  <span className="min-w-0 truncate">
                    {line.quantity} × {line.title}
                  </span>
                  <span className="shrink-0">{rupees(line.price * line.quantity)}</span>
                </li>
              ))}
            </ul>
            <div className="border-t border-gray-100 pt-3 space-y-2">
              <Row label="Items" value={quote ? rupees(quote.subtotal) : '...'} />
              <Row label="Delivery" value={quote ? (quote.shippingFee ? rupees(quote.shippingFee) : 'Free') : '...'} />
              <Row label="Order total" value={quote ? rupees(quote.total) : '...'} strong />
            </div>
            {error && (
              <p role="alert" className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-xl p-3">
                {error}
              </p>
            )}
            <button
              type="submit"
              disabled={placing || !quote}
              className="w-full bg-maroon-700 hover:bg-maroon-800 text-white font-bold py-3.5 rounded-xl transition-all shadow-lg shadow-maroon-900/20 disabled:opacity-50"
            >
              {placing ? 'Placing your order...' : 'Place order'}
            </button>
            <Link to="/cart" className="block text-center text-sm font-bold text-maroon-700 hover:underline">
              Back to cart
            </Link>
          </aside>
        </div>
      </form>
    </div>
  )
}
