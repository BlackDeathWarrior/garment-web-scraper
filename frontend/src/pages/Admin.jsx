import { useCallback, useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { FiAlertTriangle, FiFastForward, FiPause, FiPlay, FiSettings, FiZap } from 'react-icons/fi'
import Navbar from '../components/Navbar'
import SupportPanel from '../components/SupportPanel'
import { StatusBadge } from './Orders'
import { api } from '../lib/api'
import { isAdmin, useUser } from '../lib/auth'
import { rupees } from '../lib/cart'
import { formatWhen } from '../lib/support'

const REFRESH_MS = 3000

/**
 * The shop's back room: every order, the clock that moves them, and two
 * switches that make something go wrong on purpose. Nothing real fails:
 * the switches exist to show what happens when it does.
 */
export default function Admin() {
  const user = useUser()
  const [orders, setOrders] = useState([])
  const [status, setStatus] = useState(null)
  const [switches, setSwitches] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const [list, simulation] = await Promise.all([api('/admin/orders'), api('/admin/simulation')])
      setOrders(list.orders)
      setStatus(simulation.status)
      setSwitches(simulation.switches)
      setError('')
    } catch (err) {
      setError(err.status === 401 ? 'Sign in again as the admin.' : err.message)
    }
  }, [])

  useEffect(() => {
    if (!isAdmin(user)) return undefined
    void load()
    const timer = setInterval(load, REFRESH_MS)
    return () => clearInterval(timer)
  }, [user, load])

  if (!isAdmin(user)) return <Navigate to="/login?next=/admin" replace />

  const change = async (changes) => {
    // Shown at once; the shop's answer then confirms it (or the next refresh corrects it).
    setSwitches((current) => ({ ...current, ...changes }))
    try {
      const result = await api('/admin/simulation', { method: 'PUT', body: changes })
      setSwitches(result.switches)
      setStatus(result.status)
    } catch (err) {
      setError(err.message)
    }
  }

  const act = async (orderId, action) => {
    try {
      await api(`/admin/orders/${orderId}/${action}`, { method: 'POST', body: {} })
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className="min-h-screen bg-[#faf8f5]">
      <Navbar />
      <div className="max-w-screen-xl mx-auto px-4 py-8 space-y-6">
        <h1 className="text-3xl font-bold text-gray-900 tracking-tight flex items-center gap-3">
          <FiSettings className="text-maroon-700" /> Operations
        </h1>
        {error && <p role="alert" className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-xl p-3">{error}</p>}

        {switches && status && (
          <section className="p-6 rounded-2xl bg-white border border-gray-200 shadow-sm" aria-label="Simulation">
            <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2 mb-1">
              <FiZap className="text-maroon-700" /> Simulation
            </h2>
            <p className="text-sm text-gray-600 mb-5">
              This is a demonstration shop: no money moves and nothing is shipped. Orders advance on a clock, and these
              switches make the shop behave as if something had gone wrong.
            </p>
            <div className="grid md:grid-cols-3 gap-4">
              <Switch
                label="Payments are failing"
                hint="Paying by UPI or card fails at checkout. Cash on delivery still works."
                on={switches.payments_down}
                onChange={(on) => change({ payments_down: on })}
              />
              <Switch
                label="The carrier is delayed"
                hint="Orders that have shipped stop moving and show as delayed."
                on={switches.carrier_delay}
                onChange={(on) => change({ carrier_delay: on })}
              />
              <div className="bg-gray-50 border border-gray-200 rounded-xl p-4">
                <label htmlFor="step-seconds" className="font-semibold text-gray-900 text-sm">
                  Seconds per step
                </label>
                <p className="text-xs text-gray-500 mb-2">How long an order stays at each stage.</p>
                <select
                  id="step-seconds"
                  value={switches.step_seconds}
                  onChange={(e) => change({ step_seconds: Number(e.target.value) })}
                  className="px-3 py-2 rounded-xl border border-gray-200 bg-white text-sm font-semibold"
                >
                  {[...new Set([5, 15, 30, 60, 300, switches.step_seconds])]
                    .sort((a, b) => a - b)
                    .map((seconds) => (
                      <option key={seconds} value={seconds}>
                        {seconds}
                      </option>
                    ))}
                </select>
              </div>
            </div>
            <p className="text-sm text-gray-600 mt-4" data-testid="shop-status">
              Payments {status.payments} · carrier {status.carrier} · {status.orders_in_progress} order
              {status.orders_in_progress === 1 ? '' : 's'} in progress · {status.delayed_orders} delayed
            </p>
          </section>
        )}

        <section className="p-6 rounded-2xl bg-white border border-gray-200 shadow-sm" aria-label="Orders">
          <h2 className="text-lg font-bold text-gray-900 mb-4">Orders</h2>
          {orders.length === 0 ? (
            <p className="text-sm text-gray-500">No orders yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[10px] font-bold text-gray-400 uppercase tracking-widest">
                    <th className="py-2 pr-4">Order</th>
                    <th className="py-2 pr-4">Shopper</th>
                    <th className="py-2 pr-4">Total</th>
                    <th className="py-2 pr-4">Status</th>
                    <th className="py-2">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {orders.map((order) => (
                    <tr key={order.id} data-order={order.id}>
                      <td className="py-3 pr-4">
                        <span className="font-semibold text-gray-900">{order.id}</span>
                        <span className="block text-xs text-gray-400">{formatWhen(order.placedAt)}</span>
                      </td>
                      <td className="py-3 pr-4">
                        {order.customer?.name}
                        <span className="block text-xs text-gray-400">{order.customer?.email}</span>
                      </td>
                      <td className="py-3 pr-4 whitespace-nowrap">
                        {rupees(order.total)}
                        <span className="block text-xs text-gray-400">{order.payment.statusLabel}</span>
                      </td>
                      <td className="py-3 pr-4">
                        <StatusBadge order={order} />
                        {order.delayed && (
                          <span className="block text-xs text-amber-700 mt-1">
                            <FiAlertTriangle className="inline" /> delayed
                          </span>
                        )}
                        {order.held && <span className="block text-xs text-gray-500 mt-1">on hold</span>}
                      </td>
                      <td className="py-3">
                        <div className="flex flex-wrap gap-2">
                          {['placed', 'packed', 'shipped', 'out_for_delivery'].includes(order.status) && (
                            <>
                              <Small onClick={() => act(order.id, 'advance')} label={`Move ${order.id} to the next step`}>
                                <FiFastForward size={12} /> Next step
                              </Small>
                              <Small onClick={() => act(order.id, order.held ? 'release' : 'hold')}>
                                {order.held ? <FiPlay size={12} /> : <FiPause size={12} />} {order.held ? 'Release' : 'Hold'}
                              </Small>
                            </>
                          )}
                          {order.status === 'return_requested' && (
                            <Small onClick={() => act(order.id, 'refund')}>Approve return and refund</Small>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <SupportPanel />
      </div>
    </div>
  )
}

function Switch({ label, hint, on, onChange }) {
  return (
    <div className={`rounded-xl p-4 border ${on ? 'bg-amber-50 border-amber-300' : 'bg-gray-50 border-gray-200'}`}>
      <label className="flex items-center justify-between gap-3 cursor-pointer">
        <span className="font-semibold text-gray-900 text-sm">{label}</span>
        <input type="checkbox" role="switch" checked={on} onChange={(e) => onChange(e.target.checked)} className="w-5 h-5 accent-maroon-700" />
      </label>
      <p className="text-xs text-gray-500 mt-1">{hint}</p>
    </div>
  )
}

function Small({ children, onClick, label }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="px-3 py-1.5 rounded-lg text-xs font-bold border border-gray-200 bg-white hover:border-maroon-300 flex items-center gap-1.5"
    >
      {children}
    </button>
  )
}
