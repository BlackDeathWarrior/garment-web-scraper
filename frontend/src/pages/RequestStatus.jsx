import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { FiArrowLeft, FiInbox, FiLock, FiPackage, FiSend, FiStar } from 'react-icons/fi'
import Navbar from '../components/Navbar'
import { isShopper, useUser } from '../lib/auth'
import {
  formatWhen,
  isRated,
  myRequests,
  newRequestId,
  rateRequest,
  readRequest,
  replyToRequest,
  requestChanges,
  requestLink,
  savedRequests,
  saveRequest,
  tokenFor,
} from '../lib/support'

const CHANGES_EVERY_MS = 4000
// While the assistant is writing, look for its answer more often.
const CHANGES_WHILE_TYPING_MS = 1500
// The assistant answers within seconds. After this long the dots would promise an answer that may not come.
const TYPING_MAX_MS = 45000
// Without webhooks the shop cannot tell us about news, so the page asks the desk itself.
const REFETCH_EVERY_MS = 20000

export const STATE_STYLES = {
  open: 'bg-amber-50 text-amber-800 border-amber-200',
  pending: 'bg-sky-50 text-sky-800 border-sky-200',
  resolved: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  closed: 'bg-gray-100 text-gray-600 border-gray-200',
}

const AUTHORS = { customer: 'You', assistant: 'Support assistant', support: 'Support', system: 'Support' }

/**
 * The shopper's message the assistant is answering right now, or null. The
 * support desk says so (`replying`: the assistant is writing an answer it will
 * send itself; when a person checks its answers first, nobody is typing yet).
 * A desk too old to say falls back on who answers (`handling`) and who wrote last.
 */
export function awaitedMessage(request) {
  if (!request || request.state === 'closed') return null
  const last = request.messages[request.messages.length - 1]
  if (!last || last.from !== 'customer') return null
  if (typeof request.replying === 'boolean') return request.replying ? last : null
  return request.handling === 'ai' ? last : null
}

/**
 * The status in words a shopper uses. The desk's own status names ("AI
 * handling", "Human assigned") are for its staff; `state` is the same for every
 * desk, and `handling` says whether a person has it.
 */
export function shopperStatus(request) {
  switch (request?.state) {
    case 'closed':
      return 'Closed'
    case 'resolved':
      return 'Solved'
    case 'pending':
      return 'Waiting for your reply'
    default:
      if (request?.handling === 'human') return 'A colleague is on it'
      if (request?.handling === 'handed_over') return 'Passed to our team'
      return 'Open'
  }
}

export default function RequestStatus() {
  const { reference } = useParams()
  return (
    <div className="min-h-screen bg-[#faf8f5]">
      <Navbar />
      <div className="max-w-3xl mx-auto px-4 py-10">
        {reference ? <RequestDetail reference={reference.toUpperCase()} /> : <RequestList />}
      </div>
    </div>
  )
}

/** A signed-in shopper's requests come from the support desk; a guest's are the ones sent from this browser. */
function RequestList() {
  const user = useUser()
  const [requests, setRequests] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!isShopper(user)) {
      setRequests(
        savedRequests()
          .filter((r) => r.token)
          .map((r) => ({ ...r, updatedAt: r.savedAt }))
      )
      return undefined
    }
    let active = true
    myRequests()
      .then((found) => active && setRequests(found))
      .catch((err) => active && setError(err.message))
    return () => {
      active = false
    }
  }, [user])

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-2 tracking-tight">Help</h1>
      <p className="text-gray-600 mb-6">
        Your requests to support.{' '}
        <Link to="/contact" className="font-bold text-maroon-700 hover:underline">
          Write to us
        </Link>
        {isShopper(user) && (
          <>
            {' '}
            or, for an order, open it under{' '}
            <Link to="/orders" className="font-bold text-maroon-700 hover:underline">
              Your orders
            </Link>
          </>
        )}
        .
      </p>
      {error && <p role="alert" className="text-sm text-red-700 mb-4">{error}</p>}
      {requests && requests.length === 0 && (
        <div className="bg-white rounded-3xl border border-gray-100 p-10 text-center">
          <FiInbox className="mx-auto text-gray-300 mb-4" size={36} />
          <p className="text-gray-600">You have not asked us anything yet.</p>
        </div>
      )}
      <ul className="space-y-3" aria-label="Your requests">
        {(requests || []).map((request) => (
          <li key={request.reference}>
            <Link
              to={requestLink(request.reference, request.token)}
              className="flex items-center justify-between gap-4 bg-white rounded-2xl border border-gray-100 px-5 py-4 hover:border-maroon-300 transition-colors"
            >
              <span className="min-w-0">
                <span className="block text-[10px] font-bold text-gray-400 uppercase tracking-widest">
                  {request.reference}
                  {request.orderId ? ` · Order ${request.orderId}` : ''}
                </span>
                <span className="block text-sm font-semibold text-gray-900 truncate">{request.subject || 'Request'}</span>
              </span>
              <span className="shrink-0 text-right">
                {request.state && (
                  <span className={`px-2.5 py-1 rounded-full text-xs font-bold border ${STATE_STYLES[request.state] || STATE_STYLES.open}`}>
                    {shopperStatus(request)}
                  </span>
                )}
                <span className="block text-xs text-gray-400 mt-1">{formatWhen(request.updatedAt)}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}

function RequestDetail({ reference }) {
  const location = useLocation()
  const user = useUser()
  // A guest's link carries the token in its fragment; a request made here is also remembered.
  const token = location.hash.replace(/^#/, '') || tokenFor(reference)
  const [request, setRequest] = useState(null)
  const [error, setError] = useState('')
  const version = useRef(undefined)
  // The message being answered and when this page first saw it unanswered.
  const awaited = useRef({ id: null, since: 0 })
  const [, setTick] = useState(0)

  const waitingFor = awaitedMessage(request)
  if (waitingFor?.id !== awaited.current.id) {
    awaited.current = { id: waitingFor?.id ?? null, since: Date.now() }
  }
  const typing = Boolean(waitingFor) && Date.now() - awaited.current.since < TYPING_MAX_MS
  const typingNow = useRef(typing)
  typingNow.current = typing

  const load = useCallback(async () => {
    try {
      const found = await readRequest(reference, token)
      version.current = found.version
      setRequest(found)
      setError('')
      if (token) saveRequest({ reference: found.reference, token, subject: found.subject })
    } catch (err) {
      setError(
        err.status === 404
          ? 'We could not find that request. Sign in, or open it from the link you were given.'
          : err.message
      )
    }
  }, [reference, token])

  useEffect(() => {
    if (!token && !user) {
      setError('We could not find that request. Sign in, or open it from the link you were given.')
      return undefined
    }
    void load()
    let lastFull = Date.now()
    let timer
    let stopped = false
    const check = async () => {
      try {
        const changes = await requestChanges(reference, token)
        // Without webhooks nothing tells us the answer has arrived, so while it is being written we ask.
        const refetchEvery = typingNow.current ? CHANGES_WHILE_TYPING_MS : REFETCH_EVERY_MS
        const stale = !changes.live && Date.now() - lastFull >= refetchEvery
        if (changes.version !== version.current || stale) {
          lastFull = Date.now()
          await load()
        }
      } catch {}
      if (stopped) return
      // Also redraws, so the dots go when their time is up.
      setTick((n) => n + 1)
      timer = setTimeout(check, typingNow.current ? CHANGES_WHILE_TYPING_MS : CHANGES_EVERY_MS)
    }
    timer = setTimeout(check, CHANGES_WHILE_TYPING_MS)
    return () => {
      stopped = true
      clearTimeout(timer)
    }
  }, [reference, token, user, load])

  return (
    <div>
      <Link to="/requests" className="inline-flex items-center gap-1.5 text-sm font-bold text-maroon-700 hover:underline mb-6">
        <FiArrowLeft size={14} /> Help
      </Link>

      {error && (
        <div role="alert" className="bg-white rounded-2xl border border-gray-200 p-6 text-gray-700">
          {error}
        </div>
      )}

      {request && (
        <>
          <div className="flex flex-wrap items-start justify-between gap-3 mb-6">
            <div className="min-w-0">
              <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">{request.reference}</p>
              <h1 className="text-2xl font-bold text-gray-900 tracking-tight break-words">{request.subject}</h1>
              {request.orderId && request.mine && (
                <Link
                  to={`/orders/${request.orderId}`}
                  className="inline-flex items-center gap-1.5 text-sm font-bold text-maroon-700 hover:underline mt-1"
                >
                  <FiPackage size={14} /> Order {request.orderId}
                </Link>
              )}
            </div>
            <span
              data-testid="request-status"
              className={`px-3 py-1 rounded-full text-xs font-bold border ${STATE_STYLES[request.state] || STATE_STYLES.open}`}
              title={request.status || undefined}
            >
              {shopperStatus(request)}
            </span>
          </div>

          <ol className="space-y-3 mb-6" aria-label="Conversation">
            {request.messages.map((message) => (
              <Message key={message.id} message={message} />
            ))}
            {typing && <Typing />}
          </ol>

          {!request.mine && (
            <p className="text-sm text-gray-500 bg-white rounded-2xl border border-gray-100 px-4 py-3">
              You are reading this as the shop's admin. Replies and ratings are the shopper's own.
            </p>
          )}
          {request.mine && (request.state === 'resolved' || request.state === 'closed') && !isRated(reference) && (
            <Rating reference={reference} token={token} subject={request.subject} />
          )}
          {request.mine && request.state === 'closed' && <Closed request={request} />}
          {request.mine && request.state === 'resolved' && (
            <p className="text-sm text-gray-500 mb-3">
              We think this is sorted. If it is not, write below and the request opens again.
            </p>
          )}
          {request.mine && request.state !== 'closed' && <Reply reference={reference} token={token} onSent={load} />}
        </>
      )}
    </div>
  )
}

function Message({ message }) {
  const mine = message.from === 'customer'
  const author = message.from === 'support' && message.name ? message.name : AUTHORS[message.from] || 'Support'
  return (
    <li className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-3 border ${
          mine ? 'bg-maroon-700 text-white border-maroon-700' : 'bg-white text-gray-800 border-gray-100'
        }`}
      >
        <p className={`text-[10px] font-bold uppercase tracking-widest mb-1 ${mine ? 'text-maroon-100' : 'text-gray-400'}`}>
          {author} · {formatWhen(message.createdAt)}
        </p>
        <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">{message.body}</p>
      </div>
    </li>
  )
}

/**
 * A closed request takes no more messages: say so, and offer a new one with
 * the old reference in it, so support can find what was said before.
 */
function Closed({ request }) {
  // An order's requests start from the order, so support knows which order it is.
  const again = request.orderId ? `/orders/${request.orderId}` : `/contact?${new URLSearchParams({ about: request.reference })}`
  return (
    <div data-testid="request-closed" className="bg-white rounded-2xl border border-gray-100 px-4 py-4 text-sm text-gray-700">
      <p className="flex items-center gap-2 font-semibold text-gray-900">
        <FiLock size={14} /> This request is closed
      </p>
      <p className="mt-1">
        Closed requests take no new messages. Need more help with this?{' '}
        <Link to={again} className="font-bold text-maroon-700 hover:underline">
          Start a new request
        </Link>
        {request.orderId ? ' from the order’s page.' : ' and we will see this one too.'}
      </p>
    </div>
  )
}

/** Three moving dots where the assistant's answer will appear. */
function Typing() {
  return (
    <li className="flex justify-start" data-testid="assistant-typing">
      <div role="status" aria-label="Support assistant is typing" className="rounded-2xl px-4 py-3 border bg-white border-gray-100">
        <p className="text-[10px] font-bold uppercase tracking-widest mb-2 text-gray-400">Support assistant</p>
        <span className="flex items-center gap-1 h-4" aria-hidden="true">
          {[0, 150, 300].map((delay) => (
            <span
              key={delay}
              className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce motion-reduce:animate-none"
              style={{ animationDelay: `${delay}ms` }}
            />
          ))}
        </span>
      </div>
    </li>
  )
}

function Reply({ reference, token, onSent }) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const requestId = useRef(newRequestId())

  const send = async (e) => {
    e.preventDefault()
    if (!text.trim()) return
    setSending(true)
    setError('')
    try {
      await replyToRequest(reference, token, text.trim(), requestId.current)
      requestId.current = newRequestId()
      setText('')
      await onSent()
    } catch (err) {
      setError(err.message)
    } finally {
      setSending(false)
    }
  }

  return (
    <form onSubmit={send} className="bg-white rounded-2xl border border-gray-100 p-4 space-y-3">
      <label htmlFor="reply" className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">
        Add a message
      </label>
      <textarea
        id="reply"
        rows={3}
        value={text}
        onChange={(e) => setText(e.target.value)}
        className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-maroon-500 outline-none bg-gray-50 text-sm"
        placeholder="Anything to add?"
      />
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      <button
        type="submit"
        disabled={sending || !text.trim()}
        className="bg-maroon-700 hover:bg-maroon-800 text-white font-bold px-6 py-2.5 rounded-xl text-sm flex items-center gap-2 disabled:opacity-50"
      >
        <FiSend size={14} /> {sending ? 'Sending...' : 'Send'}
      </button>
    </form>
  )
}

function Rating({ reference, token, subject }) {
  const [rating, setRating] = useState(0)
  const [comment, setComment] = useState('')
  const [state, setState] = useState('ask')
  const [error, setError] = useState('')

  const submit = async (e) => {
    e.preventDefault()
    if (!rating) return
    setError('')
    try {
      await rateRequest(reference, token, rating, comment.trim() || undefined)
      // Remembered here, so the question is not asked again on the next visit.
      saveRequest({ reference, token, subject, rated: true })
      setState('done')
    } catch (err) {
      setError(err.message)
    }
  }

  if (state === 'done') {
    return (
      <p className="bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-2xl px-4 py-3 text-sm mb-4">
        Thank you for the rating.
      </p>
    )
  }

  return (
    <form onSubmit={submit} className="bg-white rounded-2xl border border-gray-100 p-4 mb-4 space-y-3">
      <p className="text-sm font-semibold text-gray-900">How did we do?</p>
      <div className="flex gap-1" role="radiogroup" aria-label="Rating">
        {[1, 2, 3, 4, 5].map((value) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={rating === value}
            aria-label={`${value} out of 5`}
            onClick={() => setRating(value)}
            className={`p-2 rounded-lg transition-colors ${value <= rating ? 'text-gold-600' : 'text-gray-300 hover:text-gray-400'}`}
          >
            <FiStar size={22} fill={value <= rating ? 'currentColor' : 'none'} />
          </button>
        ))}
      </div>
      <input
        type="text"
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        aria-label="Comment"
        placeholder="Anything we should know? (optional)"
        className="w-full px-4 py-2.5 rounded-xl border border-gray-200 focus:ring-2 focus:ring-maroon-500 outline-none bg-gray-50 text-sm"
      />
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      <button
        type="submit"
        disabled={!rating}
        className="bg-maroon-700 hover:bg-maroon-800 text-white font-bold px-6 py-2.5 rounded-xl text-sm disabled:opacity-50"
      >
        Send rating
      </button>
    </form>
  )
}
