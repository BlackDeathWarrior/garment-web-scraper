import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { FiFlag } from 'react-icons/fi'
import {
  createRequest,
  currentVisitor,
  getSupportConfig,
  newRequestId,
  requestLink,
} from '../lib/support'

/** "Report a problem with this listing": a support request that carries the listing with it. */
export default function ReportListing({ product }) {
  const [config, setConfig] = useState(null)
  const [open, setOpen] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [receipt, setReceipt] = useState(null)
  const requestId = useRef(newRequestId())
  const visitor = currentVisitor()

  useEffect(() => {
    let active = true
    getSupportConfig().then((found) => {
      if (active) setConfig(found)
    })
    return () => {
      active = false
    }
  }, [])

  // Another listing is another report.
  useEffect(() => {
    setOpen(false)
    setReceipt(null)
    setError('')
    requestId.current = newRequestId()
  }, [product?.id])

  if (!config?.tickets || !product?.id) return null

  const submit = async (e) => {
    e.preventDefault()
    const fields = new FormData(e.target)
    setSending(true)
    setError('')
    try {
      const made = await createRequest({
        kind: 'listing',
        productId: product.id,
        issue: fields.get('issue'),
        name: fields.get('name'),
        email: fields.get('email'),
        message: fields.get('message'),
        subject: `${product.title}`,
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
      <div className="mt-4 bg-emerald-50 border border-emerald-200 rounded-xl p-4 text-sm text-emerald-900">
        <p className="font-semibold">
          Thank you. Your report is <span data-testid="request-reference">{receipt.reference}</span>.
        </p>
        <Link to={requestLink(receipt.reference, receipt.token)} className="font-bold text-maroon-700 hover:underline">
          Follow this request
        </Link>
      </div>
    )
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-4 w-full text-xs font-bold text-gray-500 hover:text-maroon-700 flex items-center justify-center gap-1.5 py-2"
      >
        <FiFlag size={12} /> Report a problem with this listing
      </button>
    )
  }

  const field =
    'w-full px-3 py-2.5 rounded-xl border border-gray-200 focus:ring-2 focus:ring-maroon-500 outline-none bg-gray-50 text-sm'

  return (
    <form onSubmit={submit} className="mt-4 bg-gray-50 border border-gray-200 rounded-2xl p-4 space-y-3" aria-label="Report a problem">
      <p className="text-xs font-bold text-gray-400 uppercase tracking-widest flex items-center gap-1.5">
        <FiFlag size={12} className="text-maroon-700" /> Report a problem
      </p>
      <select name="issue" aria-label="What is wrong" className={`${field} font-medium bg-white`}>
        {(config.issues || []).map((issue) => (
          <option key={issue.key} value={issue.key}>
            {issue.label}
          </option>
        ))}
      </select>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <input name="name" required defaultValue={visitor.name} aria-label="Your name" placeholder="Your name" className={`${field} bg-white`} />
        <input name="email" type="email" required defaultValue={visitor.email} aria-label="Email address" placeholder="Email address" className={`${field} bg-white`} />
      </div>
      <textarea name="message" required rows={3} aria-label="What did you see" placeholder="What did you see?" className={`${field} bg-white`} />
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={sending}
          className="bg-maroon-700 hover:bg-maroon-800 text-white font-bold px-5 py-2.5 rounded-xl text-sm disabled:opacity-50"
        >
          {sending ? 'Sending...' : 'Send report'}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="text-sm font-bold text-gray-500 px-3">
          Cancel
        </button>
      </div>
    </form>
  )
}
