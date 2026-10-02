import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { FiMail, FiMessageSquare, FiSend, FiCheckCircle, FiShield, FiUser } from 'react-icons/fi'
import Navbar from '../components/Navbar'
import {
  createRequest,
  currentVisitor,
  getSupportConfig,
  newRequestId,
  requestLink,
} from '../lib/support'

export default function Contact() {
  const [submitted, setSubmitted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [supportDesk, setSupportDesk] = useState(false)
  const [receipt, setReceipt] = useState(null)
  const [error, setError] = useState('')
  // One id per message: sending the same one twice creates one request.
  const requestId = useRef(newRequestId())
  const visitor = currentVisitor()

  useEffect(() => {
    let active = true
    getSupportConfig().then((config) => {
      if (active) setSupportDesk(Boolean(config.tickets))
    })
    return () => {
      active = false
    }
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    const fields = new FormData(e.target)
    const data = {
      name: fields.get('name'),
      email: fields.get('email'),
      subject: fields.get('subject'),
      message: fields.get('message')
    }

    if (supportDesk) {
      try {
        const made = await createRequest({ ...data, kind: 'contact', requestId: requestId.current })
        requestId.current = newRequestId()
        setReceipt(made)
        setSubmitted(true)
      } catch (err) {
        setError(err.message || 'Failed to send message. Please try again.')
      } finally {
        setLoading(false)
      }
      return
    }

    try {
      const response = await fetch("https://formspree.io/f/xvzdraja", {
        method: "POST",
        body: JSON.stringify(data),
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        }
      })
      
      if (response.ok) {
        setSubmitted(true)
      } else {
        const result = await response.json()
        alert(result.error || "Failed to send message. Please try again.")
      }
    } catch (err) {
      alert("Connection error. Please check your internet and try again.")
    } finally {
      setLoading(false)
    }
  }

  if (submitted) {
    return (
      <div className="min-h-screen bg-[#faf8f5]">
        <Navbar search="" onSearch={() => {}} productCount={null} />
        <div className="max-w-2xl mx-auto px-4 py-20 text-center">
          <div className="inline-flex items-center justify-center w-20 h-20 bg-emerald-100 text-emerald-600 rounded-full mb-6">
            <FiCheckCircle size={40} />
          </div>
          <h1 className="text-3xl font-bold text-gray-900 mb-4">Message Received!</h1>
          <p className="text-gray-600 mb-8">
            Thank you for helping us improve Ethnic Threads. We'll get back to you shortly.
          </p>
          {receipt?.reference && (
            <div className="mb-8 flex justify-center">
              <div className="bg-white border border-gray-200 rounded-2xl px-6 py-4 text-left">
                <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Your reference</p>
                <p className="text-xl font-bold text-gray-900" data-testid="request-reference">{receipt.reference}</p>
                <Link
                  to={requestLink(receipt.reference, receipt.token)}
                  className="text-sm font-bold text-maroon-700 hover:underline"
                >
                  Follow this request
                </Link>
              </div>
            </div>
          )}
          <button
            onClick={() => { setSubmitted(false); setReceipt(null) }}
            className="bg-maroon-700 text-white px-8 py-3 rounded-xl font-bold hover:bg-maroon-800 transition-all"
          >
            Send Another Message
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#faf8f5]">
      <Navbar search="" onSearch={() => {}} productCount={null} />
      <div className="max-w-4xl mx-auto px-4 py-12">
        <div className="grid md:grid-cols-2 gap-12 items-start">
          <div className="space-y-8">
            <div>
              <h1 className="text-4xl font-bold text-gray-900 mb-4 tracking-tight">Write to Us</h1>
              <p className="text-gray-600 leading-relaxed">
                Have a feature suggestion or found a bug? We'd love to hear from you. 
                Your feedback helps us build the best ethnic wear collection in the cloud.
              </p>
            </div>

            <div className="space-y-6">
              <ContactInfo 
                icon={<FiMail className="text-maroon-700" />} 
                title="Email Us" 
                detail="prithvijay2006@gmail.com" 
              />
              <ContactInfo 
                icon={<FiShield className="text-maroon-700" />} 
                title="Report a Bug" 
                detail="Help us squash technical issues" 
              />
              <ContactInfo 
                icon={<FiMessageSquare className="text-maroon-700" />} 
                title="Feature Requests" 
                detail="Tell us what you want to see next" 
              />
            </div>
          </div>

          <form onSubmit={handleSubmit} className="bg-white p-8 rounded-3xl shadow-xl shadow-maroon-900/5 border border-gray-100 space-y-6">
            {error && (
              <div role="alert" className="bg-red-50 border-l-4 border-red-500 p-4 text-red-700 text-sm">
                {error}
              </div>
            )}
            <div className="grid grid-cols-1 gap-6">
              <div className="space-y-2">
                <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Your Name</label>
                <div className="relative">
                  <FiUser className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400" />
                  <input type="text" name="name" required defaultValue={visitor.name} className="w-full pl-11 pr-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-maroon-500 outline-none bg-gray-50 text-sm" placeholder="John Doe" />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Email Address</label>
                <div className="relative">
                  <FiMail className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400" />
                  <input type="email" name="email" required defaultValue={visitor.email} className="w-full pl-11 pr-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-maroon-500 outline-none bg-gray-50 text-sm" placeholder="john@example.com" />
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Subject</label>
              <select name="subject" className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-maroon-500 outline-none bg-gray-50 text-sm font-medium">
                <option value="Feature Suggestion">Suggest a Feature</option>
                <option value="Bug Report">Report a Bug</option>
                <option value="General Feedback">General Feedback</option>
              </select>
            </div>

            <div className="space-y-2">
              <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Your Message</label>
              <textarea 
                name="message"
                required
                rows={4}
                className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-maroon-500 outline-none bg-gray-50 text-sm"
                placeholder="How can we help?"
              />
            </div>

            <button 
              type="submit"
              disabled={loading}
              className="w-full bg-maroon-700 hover:bg-maroon-800 text-white font-bold py-4 rounded-xl transition-all shadow-lg shadow-maroon-900/20 flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {loading ? 'Sending...' : <><FiSend /> Send Message</>}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}

function ContactInfo({ icon, title, detail }) {
  return (
    <div className="flex items-center gap-4">
      <div className="w-12 h-12 bg-white rounded-2xl shadow-sm border border-gray-100 flex items-center justify-center shrink-0">
        {icon}
      </div>
      <div>
        <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">{title}</p>
        <p className="text-gray-900 font-semibold">{detail}</p>
      </div>
    </div>
  )
}
