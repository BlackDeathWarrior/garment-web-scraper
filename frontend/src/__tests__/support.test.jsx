import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Contact from '../pages/Contact'
import RequestStatus from '../pages/RequestStatus'
import ReportListing from '../components/ReportListing'
import SupportPanel from '../components/SupportPanel'
import SupportWidget from '../components/SupportWidget'
import {
  createRequest,
  getSupportConfig,
  productContext,
  requestLink,
  resetSupportConfig,
  savedRequests,
  setSupportContext,
  tokenFor,
} from '../lib/support'

const ISSUES = [
  { key: 'wrong-price', label: 'Wrong price' },
  { key: 'out-of-stock', label: 'Out of stock' },
]

/** Answers fetch by "METHOD path"; records every call. */
function stubFetch(routes) {
  const calls = []
  const fetchMock = vi.fn(async (url, init = {}) => {
    const method = init.method || 'GET'
    const call = { url: String(url), method, headers: init.headers || {}, body: init.body ? JSON.parse(init.body) : undefined }
    calls.push(call)
    const key = Object.keys(routes).find((route) => `${method} ${call.url}`.startsWith(route))
    const answer = key ? routes[key] : { status: 404, body: { message: 'not stubbed' } }
    const { status = 200, body = {} } = typeof answer === 'function' ? answer(call) : answer
    return { ok: status >= 200 && status < 300, status, json: async () => body }
  })
  vi.stubGlobal('fetch', fetchMock)
  return calls
}

const deskOn = { body: { ok: true, tickets: true, widget: null, issues: ISSUES } }
const deskOff = { body: { ok: true, tickets: false, widget: null, issues: ISSUES } }

beforeEach(() => {
  localStorage.clear()
  resetSupportConfig()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function fillContact() {
  fireEvent.change(screen.getByPlaceholderText('John Doe'), { target: { value: 'Asha Verma' } })
  fireEvent.change(screen.getByPlaceholderText('john@example.com'), { target: { value: 'asha@shopper.example' } })
  fireEvent.change(screen.getByPlaceholderText('How can we help?'), { target: { value: 'The saree filter shows kurtas.' } })
}

describe('Contact', () => {
  it('raises a support request and shows its reference', async () => {
    const calls = stubFetch({
      'GET /api/support/config': deskOn,
      'POST /api/support/tickets': { status: 201, body: { ok: true, reference: 'TMS-41', token: 'abc123' } },
    })
    render(<MemoryRouter><Contact /></MemoryRouter>)
    await waitFor(() => expect(calls.length).toBe(1))
    fillContact()
    fireEvent.click(screen.getByRole('button', { name: /send message/i }))

    expect(await screen.findByTestId('request-reference')).toHaveTextContent('TMS-41')
    expect(screen.getByRole('link', { name: /follow this request/i })).toHaveAttribute('href', '/requests/TMS-41#abc123')

    const sent = calls.find((c) => c.method === 'POST')
    expect(sent.url).toBe('/api/support/tickets')
    expect(sent.body).toMatchObject({
      kind: 'contact',
      name: 'Asha Verma',
      email: 'asha@shopper.example',
      subject: 'Feature Suggestion',
      message: 'The saree filter shows kurtas.',
    })
    expect(sent.body.requestId.length).toBeGreaterThanOrEqual(8)
    // Remembered in this browser, so "My Requests" can open it later.
    expect(tokenFor('tms-41')).toBe('abc123')
  })

  it('says why a request was refused and keeps the form', async () => {
    stubFetch({
      'GET /api/support/config': deskOn,
      'POST /api/support/tickets': { status: 429, body: { message: 'You have sent several requests already. Please try again later.' } },
    })
    render(<MemoryRouter><Contact /></MemoryRouter>)
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    fillContact()
    fireEvent.click(screen.getByRole('button', { name: /send message/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('several requests already')
    expect(screen.getByPlaceholderText('How can we help?')).toHaveValue('The saree filter shows kurtas.')
  })

  it('still uses the old form service when no support desk is set up', async () => {
    const calls = stubFetch({
      'GET /api/support/config': deskOff,
      'POST https://formspree.io/': { body: { ok: true } },
    })
    render(<MemoryRouter><Contact /></MemoryRouter>)
    await waitFor(() => expect(calls.length).toBe(1))
    fillContact()
    fireEvent.click(screen.getByRole('button', { name: /send message/i }))
    expect(await screen.findByText('Message Received!')).toBeInTheDocument()
    expect(calls.some((c) => c.url.startsWith('https://formspree.io/'))).toBe(true)
    expect(calls.some((c) => c.url === '/api/support/tickets')).toBe(false)
    expect(screen.queryByTestId('request-reference')).toBeNull()
  })
})

describe('ReportListing', () => {
  const product = { id: 'kurta-001', title: 'Cotton Straight Kurta', source: 'myntra', price_current: 1499 }

  it('sends the listing id and the issue, not the listing itself', async () => {
    const calls = stubFetch({
      'GET /api/support/config': deskOn,
      'POST /api/support/tickets': { status: 201, body: { ok: true, reference: 'TMS-42', token: 'def456' } },
    })
    render(<MemoryRouter><ReportListing product={product} /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: /report a problem with this listing/i }))
    fireEvent.change(screen.getByLabelText('What is wrong'), { target: { value: 'out-of-stock' } })
    fireEvent.change(screen.getByLabelText('Your name'), { target: { value: 'Asha Verma' } })
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'asha@shopper.example' } })
    fireEvent.change(screen.getByLabelText('What did you see'), { target: { value: 'Myntra says sold out.' } })
    fireEvent.click(screen.getByRole('button', { name: /send report/i }))

    expect(await screen.findByTestId('request-reference')).toHaveTextContent('TMS-42')
    const sent = calls.find((c) => c.method === 'POST')
    expect(sent.body).toMatchObject({ kind: 'listing', productId: 'kurta-001', issue: 'out-of-stock' })
    expect(sent.body.price_current).toBeUndefined()
  })

  it('is not shown when no support desk is set up', async () => {
    stubFetch({ 'GET /api/support/config': deskOff })
    const { container } = render(<MemoryRouter><ReportListing product={product} /></MemoryRouter>)
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })
})

describe('RequestStatus', () => {
  const request = {
    ok: true,
    reference: 'TMS-41',
    subject: 'Bug Report: The saree filter shows kurtas.',
    status: 'Resolved',
    state: 'resolved',
    version: 'd-1',
    messages: [
      { id: 'm1', from: 'customer', name: null, body: 'The saree filter shows kurtas.', createdAt: '2026-10-02T10:00:00.000Z' },
      { id: 'm2', from: 'support', name: 'Maya', body: 'Fixed, thank you.', createdAt: '2026-10-02T10:05:00.000Z' },
    ],
  }

  function open(path) {
    return render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/requests" element={<RequestStatus />} />
          <Route path="/requests/:reference" element={<RequestStatus />} />
        </Routes>
      </MemoryRouter>
    )
  }

  it('shows the conversation, sends a reply and a rating with the token from the link', async () => {
    const calls = stubFetch({
      'GET /api/support/requests/TMS-41/changes': { body: { ok: true, version: 'd-1', live: true } },
      'GET /api/support/requests/TMS-41': { body: request },
      'POST /api/support/requests/TMS-41/messages': { status: 201, body: { ok: true } },
      'POST /api/support/requests/TMS-41/rating': { body: { ok: true } },
    })
    open('/requests/tms-41#abc123')
    expect(await screen.findByTestId('request-status')).toHaveTextContent('Resolved')
    expect(screen.getByText('Fixed, thank you.')).toBeInTheDocument()
    expect(screen.getByText(/Maya/)).toBeInTheDocument()
    expect(calls[0].headers['X-Request-Token']).toBe('abc123')

    fireEvent.change(screen.getByLabelText('Add a message'), { target: { value: 'Thanks!' } })
    fireEvent.click(screen.getByRole('button', { name: /^send$/i }))
    await waitFor(() => expect(calls.some((c) => c.url.endsWith('/messages'))).toBe(true))
    const reply = calls.find((c) => c.url.endsWith('/messages'))
    expect(reply.body.message).toBe('Thanks!')
    expect(reply.headers['X-Request-Token']).toBe('abc123')

    fireEvent.click(screen.getByRole('radio', { name: '5 out of 5' }))
    fireEvent.click(screen.getByRole('button', { name: /send rating/i }))
    expect(await screen.findByText('Thank you for the rating.')).toBeInTheDocument()
    expect(calls.find((c) => c.url.endsWith('/rating')).body).toEqual({ rating: 5 })
  })

  it('does not ask the worker for a request it holds no token for', async () => {
    const calls = stubFetch({})
    open('/requests/TMS-99')
    expect(await screen.findByRole('alert')).toHaveTextContent('could not find that request')
    expect(calls).toEqual([])
  })

  it('lists the requests made in this browser', async () => {
    stubFetch({
      'POST /api/support/tickets': { status: 201, body: { ok: true, reference: 'TMS-41', token: 'abc123' } },
    })
    await createRequest({ kind: 'contact', subject: 'Bug Report', message: 'x', requestId: 'r-12345678' })
    open('/requests')
    expect(screen.getByRole('link', { name: /TMS-41/ })).toHaveAttribute('href', '/requests/TMS-41#abc123')
  })
})

describe('SupportPanel', () => {
  it('shows open incidents, requests and what the support desk reported back', async () => {
    localStorage.setItem('scraper_user_role', 'admin')
    localStorage.setItem('scraper_auth_token', 'v1.123.sig')
    const calls = stubFetch({
      'GET /api/support/admin/overview': {
        body: {
          ok: true,
          configured: { tickets: true, incidents: true, webhooks: true },
          incidents: [
            { id: 'i1', fingerprint: 'scraper.run_failed', title: 'Scraper run failed (exit code 1)', occurrences: 3, firstSeenAt: '2026-10-02T09:00:00.000Z', ticket: 'TMS-7' },
          ],
          tickets: [{ reference: 'TMS-41', subject: 'Bug Report: filter', status: 'In Progress' }],
          events: [
            { id: 'e1', type: 'message.created', reference: 'TMS-41', at: '2026-10-02T10:05:00.000Z', message: { from: 'support', name: 'Maya', preview: 'Fixed, thank you.' } },
            { id: 'e2', type: 'csat.submitted', reference: 'TMS-41', at: '2026-10-02T10:06:00.000Z', rating: 5 },
          ],
        },
      },
    })
    render(<MemoryRouter><SupportPanel /></MemoryRouter>)
    expect(await screen.findByText('Scraper run failed (exit code 1)')).toBeInTheDocument()
    expect(screen.getByText(/Reported 3 times/)).toBeInTheDocument()
    expect(screen.getByText('Maya: Fixed, thank you.')).toBeInTheDocument()
    expect(screen.getByText('5 out of 5')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /TMS-41/ })).toHaveAttribute('href', '/requests/TMS-41')
    // The admin's session goes with the call.
    expect(calls[0].headers.Authorization).toBe('Bearer v1.123.sig')
  })

  it('asks for a new sign-in when the session is not accepted', async () => {
    stubFetch({ 'GET /api/support/admin/overview': { status: 401, body: { message: 'Sign in as the admin to see this.' } } })
    render(<MemoryRouter><SupportPanel /></MemoryRouter>)
    expect(await screen.findByText('Sign in again to see the support desk.')).toBeInTheDocument()
  })
})

describe('SupportWidget', () => {
  const widget = {
    script: 'http://desk.test/widget/tms-chat.js',
    server: 'http://desk.test',
    integration: 'ethnic-threads',
  }
  let chat

  beforeEach(() => {
    chat = { setContext: vi.fn(), destroy: vi.fn() }
    // The desk's script is already on the page, so nothing is fetched from it here.
    window.TMSChat = { init: vi.fn(() => chat) }
  })

  afterEach(() => {
    delete window.TMSChat
  })

  it('starts the chat in the site colours, as the visitor, and follows the open listing', async () => {
    localStorage.setItem('scraper_current_user', JSON.stringify({ username: 'asha', email: 'asha@shopper.example' }))
    stubFetch({ 'GET /api/support/config': { body: { ok: true, tickets: true, widget, issues: [] } } })
    const { unmount } = render(<MemoryRouter><SupportWidget /></MemoryRouter>)
    await waitFor(() => expect(window.TMSChat.init).toHaveBeenCalledTimes(1))
    expect(window.TMSChat.init.mock.calls[0][0]).toMatchObject({
      server: 'http://desk.test',
      integration: 'ethnic-threads',
      theme: { primary: '#8B1A1A' },
      strings: { title: 'Ethnic Threads support' },
      visitor: { name: 'asha', email: 'asha@shopper.example' },
      identityToken: undefined,
    })

    setSupportContext({ product_id: 'k1', title: 'Kurta' })
    expect(chat.setContext).toHaveBeenCalledWith({ product_id: 'k1', title: 'Kurta' })

    unmount()
    expect(chat.destroy).toHaveBeenCalled()
    setSupportContext({})
  })

  it('vouches for the signed-in admin with a token the worker signed', async () => {
    localStorage.setItem('scraper_user_role', 'admin')
    localStorage.setItem('scraper_auth_token', 'v1.123.sig')
    const calls = stubFetch({
      'GET /api/support/config': { body: { ok: true, tickets: true, widget, issues: [] } },
      'GET /api/support/identity': { body: { ok: true, token: 'signed.identity.token' } },
    })
    render(<MemoryRouter><SupportWidget /></MemoryRouter>)
    await waitFor(() => expect(window.TMSChat.init).toHaveBeenCalledTimes(1))
    expect(window.TMSChat.init.mock.calls[0][0].identityToken).toBe('signed.identity.token')
    expect(calls.find((c) => c.url.endsWith('/identity')).headers.Authorization).toBe('Bearer v1.123.sig')
  })

  it('does nothing when no support desk is set up', async () => {
    stubFetch({ 'GET /api/support/config': deskOff })
    render(<MemoryRouter><SupportWidget /></MemoryRouter>)
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    await Promise.resolve()
    expect(window.TMSChat.init).not.toHaveBeenCalled()
  })
})

describe('support helpers', () => {
  it('treats an unreachable worker as "support is off"', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))
    expect(await getSupportConfig()).toEqual({ tickets: false, widget: null, issues: [] })
  })

  it('keeps the tracking token out of the path and tells support only what a listing shows', () => {
    expect(requestLink('TMS-41', 'abc123')).toBe('/requests/TMS-41#abc123')
    expect(productContext({ id: 'k1', title: 'Kurta', source: 'myntra', price_current: 999, image_url: 'x', rating: null })).toEqual({
      product_id: 'k1',
      title: 'Kurta',
      source: 'myntra',
      price_current: 999,
    })
    expect(savedRequests()).toEqual([])
  })
})
