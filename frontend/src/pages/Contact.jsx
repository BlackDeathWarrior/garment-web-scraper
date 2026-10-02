import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { FiCheckCircle, FiMail, FiPackage, FiSend, FiUser } from 'react-icons/fi'
import Navbar from '../components/Navbar'
import { isShopper, useUser } from '../lib/auth'
import { createRequest, getSupportConfig, newRequestId, requestLink } from '../lib/support'

/** A general message to support. Questions about an order start from the order's own page. */
export default function Contact() {
  const user = useUser()
  const [config, setConfig] = useState(null)
  const [receipt, setReceipt] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  // One id per message: sending the same one twice creates one request.
  const requestId = useRef(newRequestId())

  useEffect(() => {
    let active = true
    getSupportConfig().then((found) => active && setConfig(found))
    return () => {
      active = false
    }
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    const fields = new FormData(e.target)
    setLoading(true)
    setError('')
    try {
      const made = await createRequest({
        kind: 'contact',
        name: fields.get('name'),
        email: fields.get('email'),
        subject: fields.get('subject'),
        message: fields.get('message'),
        requestId: requestId.current,
      })
      requestId.current = newRequestId()
      setReceipt(made)
    } catch (err) {
      setError(err.message || 'Failed to send message. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  if (receipt) {
    return (
      <div className="min-h-screen bg-[#faf8f5]">
        <Navbar />
        <div className="max-w-2xl mx-auto px-4 py-20 text-center">
          <div className="inline-flex items-center justify-center w-20 h-20 bg-emerald-100 text-emerald-600 rounded-full mb-6">
            <FiCheckCircle size={40} />
          </div>
          <h1 className="text-3xl font-bold text-gray-900 mb-4">Message received</h1>
          <p className="text-gray-600 mb-8">Thank you. We will get back to you shortly.</p>
          <div className="mb-8 flex justify-center">
            <div className="bg-white border border-gray-200 rounded-2xl px-6 py-4 text-left">
              <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Your reference</p>
              <p className="text-xl font-bold text-gray-900" data-testid="request-reference">
                {receipt.reference}
              </p>
              <Link to={requestLink(receipt.reference, receipt.token)} className="text-sm font-bold text-maroon-700 hover:underline">
                Follow this request
              </Link>
            </div>
          </div>
          <button
            onClick={() => setReceipt(null)}
            className="bg-maroon-700 text-white px-8 py-3 rounded-xl font-bold hover:bg-maroon-800 transition-all"
          >
            Send another message
          </button>
        </div>
      </div>
    )
  }

  const field =
    'w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-maroon-500 outline-none bg-gray-50 text-sm'
  const label = 'text-[10px] font-bold text-gray-400 uppercase tracking-widest'

  return (
    <div className="min-h-screen bg-[#faf8f5]">
      <Navbar />
      <div className="max-w-4xl mx-auto px-4 py-12">
        <div className="grid md:grid-cols-2 gap-12 items-start">
          <div className="space-y-6">
            <div>
              <h1 className="text-4xl font-bold text-gray-900 mb-4 tracking-tight">Write to us</h1>
              <p className="text-gray-600 leading-relaxed">
                A question about a product, a problem with the site, or something we could do better: tell us here.
              </p>
            </div>
            <div className="bg-white border border-gray-100 rounded-2xl p-5 flex gap-4">
              <FiPackage className="text-maroon-700 mt-1 shrink-0" size={20} />
              <p className="text-sm text-gray-700">
                <span className="font-semibold text-gray-900">Is it about an order?</span> Open the order under{' '}
                <Link to="/orders" className="font-bold text-maroon-700 hover:underline">
                  Your orders
                </Link>{' '}
                and choose "Get help with this order". We then know which order you mean.
              </p>
            </div>
          </div>

          {!config ? null : !config.tickets ? (
            <p className="bg-white p-8 rounded-3xl border border-gray-100 text-gray-600">
              Support requests are not available at the moment. Please try again later.
            </p>
          ) : (
            <form
              onSubmit={handleSubmit}
              className="bg-white p-8 rounded-3xl shadow-xl shadow-maroon-900/5 border border-gray-100 space-y-6"
            >
              {error && (
                <div role="alert" className="bg-red-50 border-l-4 border-red-500 p-4 text-red-700 text-sm">
                  {error}
                </div>
              )}
              {isShopper(user) ? (
                <p className="text-sm text-gray-600">
                  Writing as <span className="font-semibold text-gray-900">{user.name}</span> ({user.email}).
                </p>
              ) : (
                <div className="grid grid-cols-1 gap-6">
                  <div className="space-y-2">
                    <label htmlFor="contact-name" className={label}>
                      Your name
                    </label>
                    <div className="relative">
                      <FiUser className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400" />
                      <input id="contact-name" type="text" name="name" required className={`${field} pl-11`} />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <label htmlFor="contact-email" className={label}>
                      Email address
                    </label>
                    <div className="relative">
                      <FiMail className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400" />
                      <input id="contact-email" type="email" name="email" required className={`${field} pl-11`} />
                    </div>
                  </div>
                </div>
              )}

              <div className="space-y-2">
                <label htmlFor="contact-subject" className={label}>
                  What is it about
                </label>
                <select id="contact-subject" name="subject" className={`${field} font-medium`}>
                  {(config.topics?.length ? config.topics : ['Feedback']).map((topic) => (
                    <option key={topic} value={topic}>
                      {topic}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-2">
                <label htmlFor="contact-message" className={label}>
                  Your message
                </label>
                <textarea id="contact-message" name="message" required rows={4} className={field} placeholder="How can we help?" />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full bg-maroon-700 hover:bg-maroon-800 text-white font-bold py-4 rounded-xl transition-all shadow-lg shadow-maroon-900/20 flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {loading ? (
                  'Sending...'
                ) : (
                  <>
                    <FiSend /> Send message
                  </>
                )}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
