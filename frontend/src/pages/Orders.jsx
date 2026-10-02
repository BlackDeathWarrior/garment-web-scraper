import { useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { FiAlertTriangle, FiPackage } from 'react-icons/fi'
import Navbar from '../components/Navbar'
import { api } from '../lib/api'
import { isShopper, useUser } from '../lib/auth'
import { rupees } from '../lib/cart'
import { formatDay, formatWhen } from '../lib/support'

export const STATUS_STYLES = {
  placed: 'bg-sky-50 text-sky-800 border-sky-200',
  packed: 'bg-sky-50 text-sky-800 border-sky-200',
  shipped: 'bg-amber-50 text-amber-800 border-amber-200',
  out_for_delivery: 'bg-amber-50 text-amber-800 border-amber-200',
  delivered: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  cancelled: 'bg-gray-100 text-gray-600 border-gray-200',
  return_requested: 'bg-violet-50 text-violet-800 border-violet-200',
  refunded: 'bg-gray-100 text-gray-600 border-gray-200',
}

export function StatusBadge({ order }) {
  return (
    <span
      data-testid="order-status"
      className={`px-3 py-1 rounded-full text-xs font-bold border whitespace-nowrap ${STATUS_STYLES[order.status]}`}
    >
      {order.statusLabel}
    </span>
  )
}

export default function Orders() {
  const user = useUser()
  const [orders, setOrders] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!isShopper(user)) return undefined
    let active = true
    const load = () =>
      api('/orders')
        .then((r) => active && setOrders(r.orders))
        .catch((err) => active && setError(err.message))
    void load()
    // Orders move while you watch.
    const timer = setInterval(load, 5000)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [user])

  if (!user) return <Navigate to="/login?next=/orders" replace />
  if (!isShopper(user)) return <Navigate to="/admin" replace />

  return (
    <div className="min-h-screen bg-[#faf8f5]">
      <Navbar />
      <div className="max-w-4xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold text-gray-900 tracking-tight mb-6">Your Orders</h1>
        {error && <p role="alert" className="text-sm text-red-700 mb-4">{error}</p>}
        {orders && orders.length === 0 && (
          <div className="bg-white rounded-3xl border border-gray-100 p-10 text-center">
            <FiPackage className="mx-auto text-gray-300 mb-4" size={36} />
            <p className="text-gray-600 mb-4">You have not ordered anything yet.</p>
            <Link to="/" className="text-maroon-700 font-bold hover:underline">
              Start shopping
            </Link>
          </div>
        )}
        <ul className="space-y-4">
          {(orders || []).map((order) => (
            <li key={order.id}>
              <Link
                to={`/orders/${order.id}`}
                className="block bg-white rounded-2xl border border-gray-100 p-5 hover:border-maroon-300 transition-colors"
              >
                <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
                  <div>
                    <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">
                      Order {order.id} · {formatWhen(order.placedAt)}
                    </p>
                    <p className="text-sm text-gray-600 mt-1">
                      {order.itemCount} item{order.itemCount === 1 ? '' : 's'} · {rupees(order.total)}
                    </p>
                  </div>
                  <StatusBadge order={order} />
                </div>
                <div className="flex items-center gap-3">
                  {order.items.slice(0, 4).map((item, index) => (
                    <img key={index} src={item.imageUrl} alt="" className="w-14 h-16 object-cover rounded-lg bg-amber-50" />
                  ))}
                  <p className="text-sm font-semibold text-gray-900 min-w-0 truncate">{order.items[0]?.title}</p>
                </div>
                {order.delayed ? (
                  <p className="mt-3 text-sm text-amber-800 flex items-center gap-1.5">
                    <FiAlertTriangle /> Delayed with the carrier
                  </p>
                ) : (
                  ['placed', 'packed', 'shipped', 'out_for_delivery'].includes(order.status) && (
                    <p className="mt-3 text-sm text-gray-600">Arriving by {formatDay(order.delivery.expected)}</p>
                  )
                )}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
