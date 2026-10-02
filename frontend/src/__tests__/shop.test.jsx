import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ProductModal from '../components/ProductModal'
import Navbar from '../components/Navbar'
import SupportPanel from '../components/SupportPanel'
import SupportWidget from '../components/SupportWidget'
import Admin from '../pages/Admin'
import Cart from '../pages/Cart'
import Checkout from '../pages/Checkout'
import Contact from '../pages/Contact'
import Login, { nextPath } from '../pages/Login'
import OrderDetail from '../pages/OrderDetail'
import RequestStatus from '../pages/RequestStatus'
import { clearSession, getSession, setSession } from '../lib/auth'
import { addToCart, cartCount, cartItems, cartSubtotal, clearCart, getCart, setQuantity } from '../lib/cart'
import { resetSupportConfig, setSupportContext, tokenFor } from '../lib/support'

const KURTA = { id: 'kurta-001', title: 'Cotton Straight Kurta', brand: 'Biba', price_current: 899, image_url: 'k.jpg' }
const SAREE = { id: 'saree-002', title: 'Banarasi Silk Saree', price_current: 2199, image_url: 's.jpg' }
const ASHA = { id: 'u1', role: 'shopper', name: 'Asha Verma', email: 'asha@shopper.example' }
const ADMIN = { id: 'admin', role: 'admin', name: 'shop_admin', email: null }

/** Answers fetch by "METHOD url" (the first route that the call starts with); records every call. */
function stubFetch(routes) {
  const calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, init = {}) => {
      const method = init.method || 'GET'
      const call = { url: String(url), method, headers: init.headers || {}, body: init.body ? JSON.parse(init.body) : undefined }
      calls.push(call)
      const key = Object.keys(routes).find((route) => `${method} ${call.url}`.startsWith(route))
      const answer = key ? routes[key] : { status: 404, body: { message: 'not stubbed' } }
      const { status = 200, body = {} } = typeof answer === 'function' ? answer(call) : answer
      return { ok: status >= 200 && status < 300, status, json: async () => body }
    })
  )
  return calls
}

/** Shows where the router is, so a test can see a navigation. */
function Where() {
  const location = useLocation()
  return <p data-testid="where">{location.pathname + location.search}</p>
}

function at(path, routes) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        {routes}
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>
  )
}

const ORDER = {
  id: 'ET-100001',
  status: 'shipped',
  statusLabel: 'Shipped',
  placedAt: '2026-10-02T10:00:00+00:00',
  items: [{ productId: 'kurta-001', title: 'Cotton Straight Kurta', brand: 'Biba', imageUrl: 'k.jpg', size: 'M', price: 899, quantity: 2 }],
  itemCount: 2,
  address: { name: 'Asha Verma', phone: '9830055555', line1: '12 MG Road', line2: '', city: 'Bengaluru', state: 'Karnataka', pincode: '560001' },
  delivery: { option: 'standard', label: 'Standard delivery', expected: '2026-10-06', carrier: 'SwiftShip', trackingNumber: 'SW000123456' },
  payment: { method: 'upi', label: 'UPI', status: 'paid', statusLabel: 'Paid' },
  subtotal: 1798,
  shippingFee: 0,
  total: 1798,
  currency: 'INR',
  delayed: false,
  timeline: [
    { key: 'placed', label: 'Order placed', at: '2026-10-02T10:00:00+00:00', done: true, current: false },
    { key: 'packed', label: 'Packed', at: '2026-10-02T10:00:30+00:00', done: true, current: false },
    { key: 'shipped', label: 'Shipped', at: '2026-10-02T10:01:00+00:00', done: true, current: true },
    { key: 'out_for_delivery', label: 'Out for delivery', at: null, done: false, current: false },
    { key: 'delivered', label: 'Delivered', at: null, done: false, current: false },
  ],
  events: [],
  canCancel: false,
  canReturn: false,
  refund: null,
}

const deskOn = {
  body: {
    ok: true,
    tickets: true,
    widget: null,
    issues: [
      { key: 'where', label: 'Where is my order?' },
      { key: 'return', label: 'Return or refund' },
    ],
    topics: ['Product question', 'Feedback'],
  },
}

beforeEach(() => {
  localStorage.clear()
  resetSupportConfig()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the cart', () => {
  it('adds, merges, keeps sizes apart and stops at five', () => {
    addToCart(KURTA, { size: 'M', quantity: 2 })
    addToCart(KURTA, { size: 'M', quantity: 2 })
    addToCart(KURTA, { size: 'L' })
    addToCart(SAREE)
    expect(getCart().map((l) => [l.productId, l.size, l.quantity])).toEqual([
      ['kurta-001', 'M', 4],
      ['kurta-001', 'L', 1],
      ['saree-002', null, 1],
    ])
    addToCart(KURTA, { size: 'M', quantity: 4 })
    expect(getCart()[0].quantity).toBe(5)
    expect(cartCount()).toBe(7)
    expect(cartSubtotal()).toBe(899 * 6 + 2199)

    setQuantity('kurta-001', 'L', 0)
    expect(getCart()).toHaveLength(2)
    // Checkout sends what and how many, never a price.
    expect(cartItems()).toEqual([
      { productId: 'kurta-001', quantity: 5, size: 'M' },
      { productId: 'saree-002', quantity: 1, size: null },
    ])
    clearCart()
    expect(getCart()).toEqual([])
  })

  it('is filled from a product, and "buy now" goes straight to checkout', () => {
    const onClose = vi.fn()
    at('/', <Route path="/" element={<><ProductModal product={KURTA} onClose={onClose} /><Navbar /></>} />)
    const modal = screen.getByRole('dialog', { name: 'Cotton Straight Kurta' })
    fireEvent.click(within(modal).getByRole('radio', { name: 'L' }))
    fireEvent.change(within(modal).getByLabelText('Quantity'), { target: { value: '2' } })
    fireEvent.click(within(modal).getByRole('button', { name: 'Add to cart' }))
    expect(within(modal).getByRole('button', { name: 'Added to cart' })).toBeInTheDocument()
    expect(getCart()).toMatchObject([{ productId: 'kurta-001', size: 'L', quantity: 2, price: 899 }])
    // The cart in the navigation bar counts it.
    expect(screen.getByTestId('cart-count')).toHaveTextContent('2')

    fireEvent.click(within(modal).getByRole('button', { name: /Buy now/ }))
    expect(onClose).toHaveBeenCalled()
    expect(screen.getByTestId('where')).toHaveTextContent('/checkout')
  })

  it('is priced by the shop, and asks a guest to sign in at checkout', async () => {
    addToCart(KURTA, { size: 'M' })
    const calls = stubFetch({
      'POST /api/checkout/quote': { body: { ok: true, subtotal: 899, shippingFee: 0, total: 899 } },
    })
    at('/cart', <Route path="/cart" element={<Cart />} />)
    const summary = await screen.findByRole('complementary', { name: 'Order summary' })
    await waitFor(() => expect(summary).toHaveTextContent('Free'))
    expect(calls[0].body).toEqual({ items: [{ productId: 'kurta-001', quantity: 1, size: 'M' }] })

    fireEvent.click(screen.getByRole('button', { name: /One more/ }))
    expect(getCart()[0].quantity).toBe(2)
    fireEvent.click(screen.getByRole('button', { name: 'Proceed to checkout' }))
    expect(screen.getByTestId('where')).toHaveTextContent('/login?next=/checkout')
  })
})

describe('signing in', () => {
  it('keeps the session and returns to where the shopper was going', async () => {
    const calls = stubFetch({ 'POST /api/auth/login': { body: { ok: true, token: 'v1.session', user: ASHA } } })
    at('/login?next=/checkout', <Route path="/login" element={<Login />} />)
    fireEvent.change(screen.getByLabelText(/Email/), { target: { value: 'asha@shopper.example' } })
    fireEvent.change(screen.getByLabelText(/Password/), { target: { value: 'kurta-lover-1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/checkout'))
    expect(getSession()).toEqual({ token: 'v1.session', user: ASHA })
    expect(calls[0].body).toEqual({ email: 'asha@shopper.example', password: 'kurta-lover-1' })
  })

  it('says what went wrong, and never leaves the site', async () => {
    stubFetch({ 'POST /api/auth/login': { status: 401, body: { message: 'The email or password is wrong.' } } })
    at('/login', <Route path="/login" element={<Login />} />)
    fireEvent.change(screen.getByLabelText(/Email/), { target: { value: 'a@b.example' } })
    fireEvent.change(screen.getByLabelText(/Password/), { target: { value: 'nope' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The email or password is wrong.')
    expect(getSession()).toBeNull()

    expect(nextPath(new URLSearchParams('next=/orders/ET-1'))).toBe('/orders/ET-1')
    expect(nextPath(new URLSearchParams('next=https://evil.example'))).toBe('/')
    expect(nextPath(new URLSearchParams('next=//evil.example'))).toBe('/')
  })
})

describe('checkout', () => {
  const routes = {
    'GET /api/checkout/options': {
      body: {
        delivery: [
          { key: 'standard', label: 'Standard delivery', fee: 49, freeOver: 499, days: 4 },
          { key: 'express', label: 'Express delivery', fee: 99, freeOver: null, days: 2 },
        ],
        payments: [
          { key: 'cod', label: 'Cash on delivery' },
          { key: 'upi', label: 'UPI' },
        ],
      },
    },
    'GET /api/addresses': { body: { addresses: [] } },
    'POST /api/checkout/quote': { body: { subtotal: 899, shippingFee: 0, total: 899 } },
  }

  function fillAddress() {
    fireEvent.change(screen.getByLabelText('Phone number'), { target: { value: '98300 55555' } })
    fireEvent.change(screen.getByLabelText('Address line 1'), { target: { value: '12 MG Road' } })
    fireEvent.change(screen.getByLabelText('City'), { target: { value: 'Bengaluru' } })
    fireEvent.change(screen.getByLabelText('State'), { target: { value: 'Karnataka' } })
    fireEvent.change(screen.getByLabelText('PIN code'), { target: { value: '560001' } })
  }

  it('places the order and opens it', async () => {
    setSession('v1.session', ASHA)
    addToCart(KURTA, { size: 'M' })
    const calls = stubFetch({
      ...routes,
      'POST /api/orders': { status: 201, body: { ok: true, order: { ...ORDER, status: 'placed' } } },
    })
    at('/checkout', <Route path="/checkout" element={<Checkout />} />)
    expect(await screen.findByLabelText('UPI')).toBeInTheDocument()
    // The name is already known.
    expect(screen.getByLabelText('Full name')).toHaveValue('Asha Verma')
    fillAddress()
    fireEvent.click(screen.getByLabelText('UPI'))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Place order' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Place order' }))

    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/orders/ET-100001?placed=1'))
    const placed = calls.find((c) => c.method === 'POST' && c.url === '/api/orders')
    expect(placed.headers.Authorization).toBe('Bearer v1.session')
    expect(placed.body).toMatchObject({
      items: [{ productId: 'kurta-001', quantity: 1, size: 'M' }],
      address: { name: 'Asha Verma', phone: '98300 55555', pincode: '560001' },
      delivery: 'standard',
      payment: 'upi',
      saveAddress: true,
    })
    // No card or account numbers are asked for, so none are sent.
    expect(JSON.stringify(placed.body)).not.toMatch(/card|cvv|upiId/i)
    expect(getCart()).toEqual([])
  })

  it('keeps the cart and says so when the payment does not go through', async () => {
    setSession('v1.session', ASHA)
    addToCart(KURTA)
    stubFetch({
      ...routes,
      'POST /api/orders': {
        status: 402,
        body: { reason: 'payment-failed', message: 'Your payment could not be completed, and you have not been charged.' },
      },
    })
    at('/checkout', <Route path="/checkout" element={<Checkout />} />)
    await screen.findByLabelText('UPI')
    fillAddress()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Place order' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Place order' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('you have not been charged')
    expect(getCart()).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Place order' })).toBeEnabled()
  })

  it('is for signed-in shoppers with something in the cart', () => {
    addToCart(KURTA)
    stubFetch({})
    const { unmount } = at('/checkout', <Route path="/checkout" element={<Checkout />} />)
    expect(screen.getByTestId('where')).toHaveTextContent('/login?next=/checkout')
    unmount()

    clearCart()
    setSession('v1.session', ASHA)
    stubFetch(routes)
    at('/checkout', <Route path="/checkout" element={<Checkout />} />)
    expect(screen.getByTestId('where')).toHaveTextContent('/cart')
  })
})

describe('an order', () => {
  const open = (order, extra = {}) => {
    setSession('v1.session', ASHA)
    const calls = stubFetch({
      'GET /api/orders/ET-100001': { body: { ok: true, order } },
      'GET /api/support/config': deskOn,
      'GET /api/support/requests': { body: { requests: [] } },
      ...extra,
    })
    at('/orders/ET-100001', <Route path="/orders/:id" element={<OrderDetail />} />)
    return calls
  }

  it('shows where it is, step by step', async () => {
    open(ORDER)
    expect(await screen.findByTestId('order-status')).toHaveTextContent('Shipped')
    const steps = screen.getAllByRole('listitem').filter((li) => li.dataset.step)
    expect(steps.map((li) => [li.dataset.step, li.dataset.done])).toEqual([
      ['placed', 'yes'],
      ['packed', 'yes'],
      ['shipped', 'yes'],
      ['out_for_delivery', 'no'],
      ['delivered', 'no'],
    ])
    expect(screen.getByRole('region', { name: 'Order tracking' })).toHaveTextContent('SwiftShip · SW000123456')
    expect(screen.getByTestId('payment-status')).toHaveTextContent('Paid')
    // It has shipped: no cancelling, and nothing to return yet.
    expect(screen.queryByRole('button', { name: 'Cancel order' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Return items' })).toBeNull()
  })

  it('says when it is late', async () => {
    open({ ...ORDER, delayed: true })
    expect(await screen.findByRole('status')).toHaveTextContent('delayed with the carrier')
  })

  it('can be cancelled before it ships, with the refund shown', async () => {
    const placed = { ...ORDER, status: 'placed', statusLabel: 'Order placed', canCancel: true }
    const cancelled = {
      ...placed,
      status: 'cancelled',
      statusLabel: 'Cancelled',
      canCancel: false,
      payment: { ...ORDER.payment, status: 'refunded', statusLabel: 'Refunded' },
      refund: { id: 'RF-000123', amount: 1798, arrivesIn: '5 to 7 business days' },
    }
    const calls = open(placed, { 'POST /api/orders/ET-100001/cancel': { body: { ok: true, order: cancelled } } })
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel order' }))
    const form = screen.getByRole('form', { name: 'Cancel this order?' })
    expect(form).toHaveTextContent('refunded at once')
    fireEvent.change(within(form).getByLabelText(/Why are you cancelling/), { target: { value: 'Ordered twice' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Yes, cancel it' }))
    expect(await screen.findByTestId('refund')).toHaveTextContent('RF-000123')
    expect(screen.getByTestId('order-status')).toHaveTextContent('Cancelled')
    expect(calls.find((c) => c.url.endsWith('/cancel')).body).toEqual({ reason: 'Ordered twice' })
  })

  it('takes a question to support with the order attached, and lists what was asked before', async () => {
    const calls = open(ORDER, {
      'POST /api/support/tickets': { status: 201, body: { ok: true, reference: 'TMS-41' } },
      'GET /api/support/requests': {
        body: {
          requests: [
            { reference: 'TMS-30', subject: 'Where is my order? Order ET-100001', status: 'Resolved', state: 'resolved', orderId: 'ET-100001' },
            { reference: 'TMS-31', subject: 'About another order', status: 'New', state: 'open', orderId: 'ET-100009' },
          ],
        },
      },
    })
    const earlier = await screen.findByRole('region', { name: 'Your requests about this order' })
    expect(within(earlier).getByRole('link', { name: /TMS-30/ })).toHaveAttribute('href', '/requests/TMS-30')
    expect(within(earlier).queryByText(/TMS-31/)).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /Get help with this order/ }))
    const form = await screen.findByRole('form', { name: 'Get help with this order' })
    fireEvent.change(within(form).getByLabelText('What is it about'), { target: { value: 'return' } })
    fireEvent.change(within(form).getByLabelText('Tell us more'), { target: { value: 'It is too small.' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Send to support' }))

    expect(await screen.findByTestId('request-reference')).toHaveTextContent('TMS-41')
    const sent = calls.find((c) => c.url === '/api/support/tickets')
    // The order's number and the question: the shop adds the order's facts itself.
    expect(sent.body).toMatchObject({ kind: 'order', orderId: 'ET-100001', issue: 'return', message: 'It is too small.' })
    expect(sent.body.total).toBeUndefined()
    expect(sent.headers.Authorization).toBe('Bearer v1.session')
  })

  it('tells the chat which order is on screen', async () => {
    const seen = []
    const { onSupportContext } = await import('../lib/support')
    const stop = onSupportContext((context) => seen.push(context))
    open(ORDER)
    await screen.findByTestId('order-status')
    expect(seen).toContainEqual({ page: 'order', order_id: 'ET-100001', order_status: 'Shipped' })
    stop()
    setSupportContext({})
  })
})

describe('help', () => {
  const request = {
    ok: true,
    reference: 'TMS-41',
    subject: 'Where is my order? Order ET-100001',
    status: 'Resolved',
    state: 'resolved',
    orderId: 'ET-100001',
    version: 'd-1',
    mine: true,
    messages: [
      { id: 'm1', from: 'customer', name: null, body: 'It was due yesterday.', createdAt: '2026-10-02T10:00:00.000Z' },
      { id: 'm2', from: 'support', name: 'Meera', body: 'It arrives today.', createdAt: '2026-10-02T10:05:00.000Z' },
    ],
  }
  const pages = (
    <>
      <Route path="/requests" element={<RequestStatus />} />
      <Route path="/requests/:reference" element={<RequestStatus />} />
    </>
  )

  it("lists the signed-in shopper's requests from the support desk", async () => {
    setSession('v1.session', ASHA)
    stubFetch({
      'GET /api/support/requests': {
        body: { requests: [{ reference: 'TMS-41', subject: request.subject, status: 'Resolved', state: 'resolved', orderId: 'ET-100001' }] },
      },
    })
    at('/requests', pages)
    const link = await screen.findByRole('link', { name: /TMS-41/ })
    expect(link).toHaveAttribute('href', '/requests/TMS-41')
    expect(link).toHaveTextContent('Order ET-100001')
  })

  it('shows the conversation to its shopper, who can reply and rate once', async () => {
    setSession('v1.session', ASHA)
    const calls = stubFetch({
      'GET /api/support/requests/TMS-41/changes': { body: { ok: true, version: 'd-1', live: true } },
      'GET /api/support/requests/TMS-41': { body: request },
      'POST /api/support/requests/TMS-41/messages': { status: 201, body: { ok: true } },
      'POST /api/support/requests/TMS-41/rating': { body: { ok: true } },
    })
    const { unmount } = at('/requests/tms-41', pages)
    expect(await screen.findByTestId('request-status')).toHaveTextContent('Resolved')
    expect(screen.getByText('It arrives today.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Order ET-100001/ })).toHaveAttribute('href', '/orders/ET-100001')
    // Signed in: the account is the key, no token in the request.
    expect(calls[0].headers['X-Request-Token']).toBeUndefined()

    fireEvent.change(screen.getByLabelText('Add a message'), { target: { value: 'Thanks!' } })
    fireEvent.click(screen.getByRole('button', { name: /^send$/i }))
    await waitFor(() => expect(calls.some((c) => c.url.endsWith('/messages'))).toBe(true))

    fireEvent.click(screen.getByRole('radio', { name: '5 out of 5' }))
    fireEvent.click(screen.getByRole('button', { name: /send rating/i }))
    expect(await screen.findByText('Thank you for the rating.')).toBeInTheDocument()
    expect(calls.find((c) => c.url.endsWith('/rating')).body).toEqual({ rating: 5 })

    // Coming back, the question is not asked again.
    unmount()
    at('/requests/TMS-41', pages)
    await screen.findByTestId('request-status')
    expect(screen.queryByText('How did we do?')).toBeNull()
  })

  it('lets the admin read a request, not answer for the shopper', async () => {
    setSession('v1.admin', ADMIN)
    stubFetch({
      'GET /api/support/requests/TMS-41/changes': { body: { ok: true, version: 'd-1', live: true } },
      'GET /api/support/requests/TMS-41': { body: { ...request, mine: false } },
    })
    at('/requests/TMS-41', pages)
    expect(await screen.findByText(/reading this as the shop's admin/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Add a message')).toBeNull()
    expect(screen.queryByText('How did we do?')).toBeNull()
  })

  it('a guest writes in with a name and email and gets a link that carries the key', async () => {
    const calls = stubFetch({
      'GET /api/support/config': deskOn,
      'POST /api/support/tickets': { status: 201, body: { ok: true, reference: 'TMS-50', token: 'abc123' } },
    })
    at('/contact', <Route path="/contact" element={<Contact />} />)
    fireEvent.change(await screen.findByLabelText('Your name'), { target: { value: 'Passing Visitor' } })
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'visitor@shopper.example' } })
    fireEvent.change(screen.getByLabelText('Your message'), { target: { value: 'Do you have this in green?' } })
    await waitFor(() => expect(screen.getByLabelText('What is it about')).toHaveValue('Product question'))
    fireEvent.click(screen.getByRole('button', { name: /Send message/ }))

    expect(await screen.findByTestId('request-reference')).toHaveTextContent('TMS-50')
    expect(screen.getByRole('link', { name: 'Follow this request' })).toHaveAttribute('href', '/requests/TMS-50#abc123')
    expect(calls.find((c) => c.method === 'POST').body).toMatchObject({
      kind: 'contact',
      name: 'Passing Visitor',
      email: 'visitor@shopper.example',
      subject: 'Product question',
    })
    expect(tokenFor('TMS-50')).toBe('abc123')
  })

  it('a signed-in shopper is not asked who they are', async () => {
    setSession('v1.session', ASHA)
    stubFetch({ 'GET /api/support/config': deskOn })
    at('/contact', <Route path="/contact" element={<Contact />} />)
    expect(await screen.findByText(/Writing as/)).toHaveTextContent('Asha Verma')
    expect(screen.queryByLabelText('Your name')).toBeNull()
  })
})

describe('the admin', () => {
  const simulation = {
    switches: { payments_down: false, carrier_delay: false, step_seconds: 30 },
    status: { payments: 'working', carrier: 'on time', orders_in_progress: 1, delayed_orders: 0 },
  }
  const routes = {
    'GET /api/admin/orders': {
      body: { orders: [{ ...ORDER, held: false, customer: { name: 'Asha Verma', email: 'asha@shopper.example' } }] },
    },
    'GET /api/admin/simulation': { body: simulation },
    'GET /api/support/admin/overview': {
      body: {
        ok: true,
        configured: { tickets: true, incidents: true, webhooks: true },
        incidents: [{ id: 'i1', fingerprint: 'shop.payments_failing', title: 'Payments are failing at checkout', occurrences: 3, firstSeenAt: '2026-10-02T09:00:00.000Z', ticket: 'TMS-7' }],
        tickets: [{ reference: 'TMS-41', subject: 'Where is my order?', status: 'New' }],
        events: [{ id: 'e1', type: 'csat.submitted', reference: 'TMS-41', at: '2026-10-02T10:06:00.000Z', rating: 5 }],
      },
    },
  }

  it('switches a problem on and pushes an order along', async () => {
    setSession('v1.admin', ADMIN)
    const calls = stubFetch({
      ...routes,
      'PUT /api/admin/simulation': {
        body: { switches: { ...simulation.switches, payments_down: true }, status: { ...simulation.status, payments: 'failing' } },
      },
      'POST /api/admin/orders/ET-100001/advance': { body: { ok: true } },
    })
    at('/admin', <Route path="/admin" element={<Admin />} />)
    fireEvent.click(await screen.findByRole('switch', { name: 'Payments are failing' }))
    await waitFor(() => expect(screen.getByTestId('shop-status')).toHaveTextContent('Payments failing'))
    expect(calls.find((c) => c.method === 'PUT').body).toEqual({ payments_down: true })

    fireEvent.click(screen.getByRole('button', { name: 'Move ET-100001 to the next step' }))
    await waitFor(() => expect(calls.some((c) => c.url.endsWith('/advance'))).toBe(true))
    expect(calls.every((c) => c.headers.Authorization === 'Bearer v1.admin')).toBe(true)

    // The support desk's side: what the shop reported, and what came back.
    expect(await screen.findByText('Payments are failing at checkout')).toBeInTheDocument()
    expect(screen.getByText(/Reported 3 times/)).toBeInTheDocument()
    expect(screen.getByText('5 out of 5')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /TMS-41/ })).toHaveAttribute('href', '/requests/TMS-41')
  })

  it('is closed to everyone else', () => {
    setSession('v1.session', ASHA)
    stubFetch(routes)
    at('/admin', <Route path="/admin" element={<Admin />} />)
    expect(screen.getByTestId('where')).toHaveTextContent('/login?next=/admin')
  })

  it('is told to sign in again when the session is refused', async () => {
    stubFetch({ 'GET /api/support/admin/overview': { status: 401, body: { message: 'Sign in as the admin to see this.' } } })
    render(<MemoryRouter><SupportPanel /></MemoryRouter>)
    expect(await screen.findByText('Sign in again to see the support desk.')).toBeInTheDocument()
  })
})

describe('the chat', () => {
  const widget = { script: 'http://desk.test/widget/tms-chat.js', server: 'http://desk.test', integration: 'ethnic-threads' }
  let chat

  beforeEach(() => {
    chat = { setContext: vi.fn(), destroy: vi.fn() }
    // The desk's script is already on the page, so nothing is fetched from it here.
    window.TMSChat = { init: vi.fn(() => chat) }
  })

  afterEach(() => {
    delete window.TMSChat
  })

  it('starts as a guest, and again as the shopper once they sign in', async () => {
    const calls = stubFetch({
      'GET /api/support/config': { body: { ok: true, tickets: true, widget, issues: [], topics: [] } },
      'GET /api/support/identity': { body: { ok: true, token: 'signed.identity.token' } },
    })
    render(<MemoryRouter><SupportWidget /></MemoryRouter>)
    await waitFor(() => expect(window.TMSChat.init).toHaveBeenCalledTimes(1))
    expect(window.TMSChat.init.mock.calls[0][0]).toMatchObject({
      server: 'http://desk.test',
      integration: 'ethnic-threads',
      theme: { primary: '#8B1A1A' },
      visitor: undefined,
      identityToken: undefined,
    })
    expect(calls.some((c) => c.url.endsWith('/identity'))).toBe(false)

    setSupportContext({ page: 'order', order_id: 'ET-100001' })
    expect(chat.setContext).toHaveBeenCalledWith({ page: 'order', order_id: 'ET-100001' })

    // Signing in: the old chat goes, a new one starts with the shop vouching for them.
    setSession('v1.session', ASHA)
    await waitFor(() => expect(window.TMSChat.init).toHaveBeenCalledTimes(2))
    expect(chat.destroy).toHaveBeenCalled()
    expect(window.TMSChat.init.mock.calls[1][0]).toMatchObject({
      visitor: { name: 'Asha Verma', email: 'asha@shopper.example' },
      identityToken: 'signed.identity.token',
    })
    clearSession()
    setSupportContext({})
  })

  it('does nothing when no support desk is set up', async () => {
    stubFetch({ 'GET /api/support/config': { body: { ok: true, tickets: false, widget: null } } })
    render(<MemoryRouter><SupportWidget /></MemoryRouter>)
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    await Promise.resolve()
    expect(window.TMSChat.init).not.toHaveBeenCalled()
  })
})
