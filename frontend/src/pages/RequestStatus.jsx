import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { FiArrowLeft, FiInbox, FiSend, FiStar } from 'react-icons/fi'
import Navbar from '../components/Navbar'
import {
  adminSession,
  formatWhen,
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
// Without webhooks the worker cannot tell us about news, so the page asks the desk itself.
const REFETCH_EVERY_MS = 20000

const STATE_STYLES = {
  open: 'bg-amber-50 text-amber-800 border-amber-200',
  pending: 'bg-sky-50 text-sky-800 border-sky-200',
  resolved: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  closed: 'bg-gray-100 text-gray-600 border-gray-200',
}

const AUTHORS = { customer: 'You', assistant: 'Support assistant', support: 'Support', system: 'Support' }

export default function RequestStatus() {
  const { reference } = useParams()
  return (
    <div className="min-h-screen bg-[#faf8f5]">
      <Navbar search="" onSearch={() => {}} productCount={null} />
      <div className="max-w-3xl mx-auto px-4 py-10">
        {reference ? <RequestDetail reference={reference.toUpperCase()} /> : <RequestList />}
      </div>
    </div>
  )
}

function RequestList() {
  const requests = savedRequests()
  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-2 tracking-tight">My Requests</h1>
      <p className="text-gray-600 mb-8">Messages and listing reports sent from this browser.</p>
      {requests.length === 0 ? (
        <div className="bg-white rounded-3xl border border-gray-100 p-10 text-center">
          <FiInbox className="mx-auto text-gray-300 mb-4" size={36} />
          <p className="text-gray-600 mb-4">You have not sent us anything yet.</p>
          <Link to="/contact" className="text-maroon-700 font-bold hover:underline">
            Write to us
          </Link>
        </div>
      ) : (
        <ul className="space-y-3">
          {requests.map((request) => (
            <li key={request.reference}>
              <Link
                to={requestLink(request.reference, request.token)}
                className="flex items-center justify-between gap-4 bg-white rounded-2xl border border-gray-100 px-5 py-4 hover:border-maroon-300 transition-colors"
              >
                <span className="min-w-0">
                  <span className="block text-[10px] font-bold text-gray-400 uppercase tracking-widest">
                    {request.reference}
                  </span>
                  <span className="block text-sm font-semibold text-gray-900 truncate">
                    {request.subject || 'Request'}
                  </span>
                </span>
                <span className="text-xs text-gray-400 shrink-0">{formatWhen(request.savedAt)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function RequestDetail({ reference }) {
  const location = useLocation()
  // The link carries the token in its fragment; a request made here is also remembered.
  const token = location.hash.replace(/^#/, '') || tokenFor(reference)
  const [request, setRequest] = useState(null)
  const [error, setError] = useState('')
  const version = useRef(undefined)

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
          ? 'We could not find that request. Open it from the link you were given, in the browser you sent it from.'
          : err.message
      )
    }
  }, [reference, token])

  useEffect(() => {
    if (!token && !adminSession()) {
      setError('We could not find that request. Open it from the link you were given, in the browser you sent it from.')
      return undefined
    }
    void load()
    let lastFull = Date.now()
    const timer = setInterval(async () => {
      try {
        const changes = await requestChanges(reference, token)
        const stale = !changes.live && Date.now() - lastFull > REFETCH_EVERY_MS
        if (changes.version !== version.current || stale) {
          lastFull = Date.now()
          await load()
        }
      } catch {}
    }, CHANGES_EVERY_MS)
    return () => clearInterval(timer)
  }, [reference, token, load])

  return (
    <div>
      <Link to="/requests" className="inline-flex items-center gap-1.5 text-sm font-bold text-maroon-700 hover:underline mb-6">
        <FiArrowLeft size={14} /> My requests
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
            </div>
            <span
              data-testid="request-status"
              className={`px-3 py-1 rounded-full text-xs font-bold border ${STATE_STYLES[request.state] || STATE_STYLES.open}`}
            >
              {request.status}
            </span>
          </div>

          <ol className="space-y-3 mb-6" aria-label="Conversation">
            {request.messages.map((message) => (
              <Message key={message.id} message={message} />
            ))}
          </ol>

          {request.state === 'resolved' && <Rating reference={reference} token={token} />}
          {request.state !== 'closed' && <Reply reference={reference} token={token} onSent={load} />}
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

function Rating({ reference, token }) {
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
