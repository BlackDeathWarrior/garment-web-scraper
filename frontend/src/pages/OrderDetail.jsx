import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { FiAlertTriangle, FiArrowLeft, FiCheck, FiCheckCircle, FiHelpCircle, FiRefreshCw, FiTruck } from 'react-icons/fi'
import Navbar from '../components/Navbar'
import { Row } from './Cart'
import { StatusBadge } from './Orders'
import { api } from '../lib/api'
import { isShopper, useUser } from '../lib/auth'
import { addToCart, rupees } from '../lib/cart'
import {
  createRequest,
  formatDay,
  formatWhen,
  getSupportConfig,
  myRequests,
  newRequestId,
  requestLink,
  setSupportContext,
} from '../lib/support'

const REFRESH_MS = 3000
const MOVING = ['placed', 'packed', 'shipped', 'out_for_delivery', 'return_requested']

export default function OrderDetail() {
  const { id } = useParams()
  const user = useUser()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [order, setOrder] = useState(null)
  const [error, setError] = useState('')
  const [action, setAction] = useState(null) // 'cancel' | 'return' | 'help'
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const found = await api(`/orders/${encodeURIComponent(id)}`)
      setOrder(found.order)
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }, [id])

  useEffect(() => {
    if (!isShopper(user)) return undefined
    void load()
    // The order moves on the shop's clock: keep the page current while it can still change.
    const timer = setInterval(load, REFRESH_MS)
    return () => clearInterval(timer)
  }, [user, load])

  // The chat widget tells support which order the shopper is looking at.
  useEffect(() => {
    if (order) setSupportContext({ page: 'order', order_id: order.id, order_status: order.statusLabel })
    return () => setSupportContext({})
  }, [order?.id, order?.statusLabel])

  if (!user) return <Navigate to={`/login?next=/orders/${id}`} replace />
  if (!isShopper(user)) return <Navigate to="/admin" replace />

  const act = async (kind, reason) => {
    setBusy(true)
    setError('')
    try {
      const changed = await api(`/orders/${order.id}/${kind}`, { method: 'POST', body: { reason } })
      setOrder(changed.order)
      setAction(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const buyAgain = () => {
    order.items.forEach((item) =>
      addToCart(
        { id: item.productId, title: item.title, brand: item.brand, image_url: item.imageUrl, price_current: item.price },
        { size: item.size, quantity: item.quantity }
      )
    )
    navigate('/cart')
  }

  return (
    <div className="min-h-screen bg-[#faf8f5]">
      <Navbar />
      <div className="max-w-4xl mx-auto px-4 py-8">
        <Link to="/orders" className="inline-flex items-center gap-1.5 text-sm font-bold text-maroon-700 hover:underline mb-5">
          <FiArrowLeft size={14} /> Your orders
        </Link>

        {error && (
          <div role="alert" className="bg-white rounded-2xl border border-red-200 p-4 text-red-700 text-sm mb-4">
            {error}
          </div>
        )}

        {order && (
          <>
            {params.get('placed') && (
              <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-4 mb-5 flex items-center gap-3 text-emerald-900">
                <FiCheckCircle size={22} className="shrink-0" />
                <p className="text-sm">
                  <span className="font-bold">Thank you, your order is placed.</span> We will keep this page up to date as
                  it moves.
                </p>
              </div>
            )}

            <div className="flex flex-wrap items-start justify-between gap-3 mb-5">
              <div>
                <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">
                  Placed {formatWhen(order.placedAt)}
                </p>
                <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Order {order.id}</h1>
              </div>
              <StatusBadge order={order} />
            </div>

            <Tracking order={order} />

            <div className="grid md:grid-cols-3 gap-5 mt-5 items-start">
              <section className="md:col-span-2 bg-white rounded-2xl border border-gray-100 p-5" aria-label="Items">
                <h2 className="text-sm font-bold text-gray-400 uppercase tracking-widest mb-4">Items</h2>
                <ul className="space-y-4">
                  {order.items.map((item, index) => (
                    <li key={index} className="flex gap-4">
                      <img src={item.imageUrl} alt="" className="w-16 h-20 object-cover rounded-xl bg-amber-50 shrink-0" />
                      <div className="min-w-0">
                        <p className="font-semibold text-gray-900 line-clamp-2">{item.title}</p>
                        <p className="text-xs text-gray-500 mt-0.5">
                          {item.size ? `Size ${item.size} · ` : ''}Quantity {item.quantity}
                        </p>
                        <p className="text-sm font-bold text-gray-900 mt-1">{rupees(item.price * item.quantity)}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>

              <div className="space-y-5">
                <section className="bg-white rounded-2xl border border-gray-100 p-5 space-y-2" aria-label="Payment">
                  <h2 className="text-sm font-bold text-gray-400 uppercase tracking-widest mb-2">Payment</h2>
                  <Row label="Items" value={rupees(order.subtotal)} />
                  <Row label="Delivery" value={order.shippingFee ? rupees(order.shippingFee) : 'Free'} />
                  <Row label="Total" value={rupees(order.total)} strong />
                  <p className="text-sm text-gray-600 pt-1">
                    {order.payment.label} · <span data-testid="payment-status">{order.payment.statusLabel}</span>
                  </p>
                  {order.refund && (
                    <p className="text-sm text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-xl p-3" data-testid="refund">
                      {rupees(order.refund.amount)} refunded ({order.refund.id}). It reaches you in {order.refund.arrivesIn}.
                    </p>
                  )}
                </section>
                <section className="bg-white rounded-2xl border border-gray-100 p-5" aria-label="Delivery address">
                  <h2 className="text-sm font-bold text-gray-400 uppercase tracking-widest mb-2">Delivering to</h2>
                  <p className="text-sm text-gray-700">
                    <span className="font-semibold text-gray-900">{order.address.name}</span>
                    <br />
                    {order.address.line1}
                    {order.address.line2 ? `, ${order.address.line2}` : ''}
                    <br />
                    {order.address.city}, {order.address.state} {order.address.pincode}
                    <br />
                    {order.address.phone}
                  </p>
                </section>
              </div>
            </div>

            <section className="bg-white rounded-2xl border border-gray-100 p-5 mt-5" aria-label="Order actions">
              <div className="flex flex-wrap gap-3">
                {order.canCancel && (
                  <ActionButton onClick={() => setAction(action === 'cancel' ? null : 'cancel')}>Cancel order</ActionButton>
                )}
                {order.canReturn && (
                  <ActionButton onClick={() => setAction(action === 'return' ? null : 'return')}>Return items</ActionButton>
                )}
                <ActionButton onClick={buyAgain}>
                  <FiRefreshCw size={14} /> Buy it again
                </ActionButton>
                <ActionButton primary onClick={() => setAction(action === 'help' ? null : 'help')}>
                  <FiHelpCircle size={14} /> Get help with this order
                </ActionButton>
              </div>

              {action === 'cancel' && (
                <ReasonForm
                  title="Cancel this order?"
                  hint={
                    order.payment.status === 'paid'
                      ? `The ${rupees(order.total)} you paid is refunded at once.`
                      : 'Nothing has been charged for it.'
                  }
                  label="Why are you cancelling? (optional)"
                  submit="Yes, cancel it"
                  busy={busy}
                  onSubmit={(reason) => act('cancel', reason)}
                />
              )}
              {action === 'return' && (
                <ReasonForm
                  title="Return this order"
                  hint="We arrange the pickup. The refund follows once the return is approved."
                  label="What is wrong with it?"
                  required
                  submit="Request a return"
                  busy={busy}
                  onSubmit={(reason) => act('return', reason)}
                />
              )}
              {action === 'help' && <HelpForm order={order} />}
            </section>

            <OrderRequests orderId={order.id} />
          </>
        )}
      </div>
    </div>
  )
}

function ActionButton({ children, onClick, primary }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-4 py-2.5 rounded-xl text-sm font-bold flex items-center gap-2 border transition-all ${
        primary
          ? 'bg-maroon-700 border-maroon-700 text-white hover:bg-maroon-800'
          : 'bg-white border-gray-200 text-gray-700 hover:border-maroon-300'
      }`}
    >
      {children}
    </button>
  )
}

/** Where the order is: five steps, the time each was reached, and the carrier once it has shipped. */
function Tracking({ order }) {
  const stopped = !order.timeline.some((step) => step.current) && order.status !== 'delivered'
  return (
    <section className="bg-white rounded-2xl border border-gray-100 p-5" aria-label="Order tracking">
      {order.delayed && (
        <p role="status" className="mb-4 bg-amber-50 border border-amber-200 text-amber-900 rounded-xl p-3 text-sm flex items-start gap-2">
          <FiAlertTriangle className="mt-0.5 shrink-0" />
          Your order is delayed with the carrier. We are sorry: it will move again as soon as they do.
        </p>
      )}
      {['cancelled', 'refunded', 'return_requested'].includes(order.status) && (
        <p role="status" className="mb-4 bg-gray-50 border border-gray-200 text-gray-700 rounded-xl p-3 text-sm">
          {order.status === 'cancelled' && 'This order was cancelled.'}
          {order.status === 'refunded' && 'This order was returned and refunded.'}
          {order.status === 'return_requested' && 'A return has been requested. We will confirm the refund here.'}
        </p>
      )}
      <ol className="grid grid-cols-5 gap-1" aria-label="Progress">
        {order.timeline.map((step, index) => (
          <li key={step.key} className="text-center" data-step={step.key} data-done={step.done ? 'yes' : 'no'}>
            <div className="flex items-center">
              <span className={`flex-1 h-1 rounded ${index === 0 ? 'opacity-0' : step.done ? 'bg-maroon-700' : 'bg-gray-200'}`} />
              <span
                className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                  step.done ? 'bg-maroon-700 text-white' : 'bg-gray-100 text-gray-400'
                } ${step.current && !stopped ? 'ring-4 ring-maroon-100' : ''}`}
              >
                {step.done ? <FiCheck size={14} /> : index + 1}
              </span>
              <span
                className={`flex-1 h-1 rounded ${
                  index === order.timeline.length - 1
                    ? 'opacity-0'
                    : order.timeline[index + 1].done
                      ? 'bg-maroon-700'
                      : 'bg-gray-200'
                }`}
              />
            </div>
            <p className={`mt-2 text-[11px] sm:text-xs font-bold ${step.done ? 'text-gray-900' : 'text-gray-400'}`}>
              {step.label}
            </p>
            {step.at && <p className="text-[10px] text-gray-500">{formatWhen(step.at)}</p>}
          </li>
        ))}
      </ol>
      <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-sm text-gray-600">
        {MOVING.includes(order.status) && order.status !== 'return_requested' && (
          <span>
            Arriving by <span className="font-semibold text-gray-900">{formatDay(order.delivery.expected)}</span> ·{' '}
            {order.delivery.label}
          </span>
        )}
        {order.delivery.carrier && (
          <span className="flex items-center gap-1.5">
            <FiTruck /> {order.delivery.carrier} · {order.delivery.trackingNumber}
          </span>
        )}
      </div>
    </section>
  )
}

function ReasonForm({ title, hint, label, required, submit, busy, onSubmit }) {
  const [reason, setReason] = useState('')
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit(reason.trim())
      }}
      className="mt-4 bg-gray-50 border border-gray-200 rounded-2xl p-4 space-y-3"
      aria-label={title}
    >
      <p className="font-semibold text-gray-900">{title}</p>
      <p className="text-sm text-gray-600">{hint}</p>
      <input
        aria-label={label}
        placeholder={label}
        required={required}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        className="w-full px-3 py-2.5 rounded-xl border border-gray-200 bg-white text-sm focus:ring-2 focus:ring-maroon-500 outline-none"
      />
      <button
        type="submit"
        disabled={busy}
        className="bg-maroon-700 hover:bg-maroon-800 text-white font-bold px-5 py-2.5 rounded-xl text-sm disabled:opacity-50"
      >
        {busy ? 'One moment...' : submit}
      </button>
    </form>
  )
}

/** "Get help with this order": a support request that carries the order with it. */
function HelpForm({ order }) {
  const [config, setConfig] = useState(null)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [receipt, setReceipt] = useState(null)
  const requestId = useRef(newRequestId())

  useEffect(() => {
    let active = true
    getSupportConfig().then((found) => active && setConfig(found))
    return () => {
      active = false
    }
  }, [])

  if (!config) return null
  if (!config.tickets) {
    return <p className="mt-4 text-sm text-gray-600">Support is not available at the moment. Please try the chat later.</p>
  }

  const submit = async (e) => {
    e.preventDefault()
    const fields = new FormData(e.target)
    setSending(true)
    setError('')
    try {
      const made = await createRequest({
        kind: 'order',
        orderId: order.id,
        issue: fields.get('issue'),
        message: fields.get('message'),
        requestId: requestId.current,
      })
      requestId.current = newRequestId()
      setReceipt(made)
    } catch (err) {
      setError(err.message)
    } finally {
      setSending(false)
    }
  }

  if (receipt) {
    return (
      <div className="mt-4 bg-emerald-50 border border-emerald-200 rounded-2xl p-4 text-sm text-emerald-900">
        <p className="font-semibold">
          We have your request: <span data-testid="request-reference">{receipt.reference}</span>.
        </p>
        <Link to={requestLink(receipt.reference)} className="font-bold text-maroon-700 hover:underline">
          Follow this request
        </Link>
      </div>
    )
  }

  const field =
    'w-full px-3 py-2.5 rounded-xl border border-gray-200 bg-white text-sm focus:ring-2 focus:ring-maroon-500 outline-none'
  return (
    <form onSubmit={submit} className="mt-4 bg-gray-50 border border-gray-200 rounded-2xl p-4 space-y-3" aria-label="Get help with this order">
      <p className="font-semibold text-gray-900">What do you need help with?</p>
      <select name="issue" aria-label="What is it about" className={`${field} font-medium`}>
        {config.issues.map((issue) => (
          <option key={issue.key} value={issue.key}>
            {issue.label}
          </option>
        ))}
      </select>
      <textarea name="message" required rows={3} aria-label="Tell us more" placeholder="Tell us more" className={field} />
      <p className="text-xs text-gray-500">We already know which order this is about: no need to copy its details.</p>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      <button
        type="submit"
        disabled={sending}
        className="bg-maroon-700 hover:bg-maroon-800 text-white font-bold px-5 py-2.5 rounded-xl text-sm disabled:opacity-50"
      >
        {sending ? 'Sending...' : 'Send to support'}
      </button>
    </form>
  )
}

/** Requests the shopper already has about this order. */
function OrderRequests({ orderId }) {
  const [requests, setRequests] = useState([])

  useEffect(() => {
    let active = true
    const load = () =>
      myRequests()
        .then((all) => active && setRequests(all.filter((r) => r.orderId === orderId)))
        .catch(() => {})
    void load()
    const timer = setInterval(load, 8000)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [orderId])

  if (!requests.length) return null
  return (
    <section className="bg-white rounded-2xl border border-gray-100 p-5 mt-5" aria-label="Your requests about this order">
      <h2 className="text-sm font-bold text-gray-400 uppercase tracking-widest mb-3">Your requests about this order</h2>
      <ul className="divide-y divide-gray-100">
        {requests.map((request) => (
          <li key={request.reference} className="py-2.5 flex items-center justify-between gap-3">
            <Link to={requestLink(request.reference)} className="min-w-0 hover:text-maroon-700">
              <span className="block text-[10px] font-bold text-gray-400 uppercase tracking-widest">{request.reference}</span>
              <span className="block text-sm font-semibold text-gray-900 truncate">{request.subject}</span>
            </Link>
            <span className="text-xs font-bold text-gray-600 bg-gray-100 rounded-full px-2.5 py-1 shrink-0">{request.status}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
