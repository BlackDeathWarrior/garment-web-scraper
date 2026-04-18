import { useState } from 'react'
import { FiMail, FiMessageSquare, FiSend, FiCheckCircle, FiShield } from 'react-icons/fi'
import Navbar from '../components/Navbar'

export default function Contact() {
  const [submitted, setSubmitted] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleSubmit = (e) => {
    e.preventDefault()
    setLoading(true)
    // Simulate submission
    setTimeout(() => {
      setLoading(false)
      setSubmitted(true)
    }, 1000)
  }

  if (submitted) {
    return (
      <div className="min-h-screen bg-[#faf8f5]">
        <Navbar />
        <div className="max-w-2xl mx-auto px-4 py-20 text-center">
          <div className="inline-flex items-center justify-center w-20 h-20 bg-emerald-100 text-emerald-600 rounded-full mb-6">
            <FiCheckCircle size={40} />
          </div>
          <h1 className="text-3xl font-bold text-gray-900 mb-4">Message Received!</h1>
          <p className="text-gray-600 mb-8">
            Thank you for helping us improve Ethnic Threads. We'll get back to you shortly.
          </p>
          <button 
            onClick={() => setSubmitted(false)}
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
      <Navbar />
      <div className="max-w-4xl mx-auto px-4 py-12">
        <div className="grid md:grid-cols-2 gap-12 items-start">
          {/* Info Side */}
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

          {/* Form Side */}
          <form onSubmit={handleSubmit} className="bg-white p-8 rounded-3xl shadow-xl shadow-maroon-900/5 border border-gray-100 space-y-6">
            <div className="space-y-2">
              <label className="text-xs font-bold text-gray-400 uppercase tracking-widest">Subject</label>
              <select className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-maroon-500 outline-none bg-gray-50 text-sm font-medium">
                <option>Suggest a Feature</option>
                <option>Report a Bug</option>
                <option>General Feedback</option>
                <option>Business Inquiry</option>
              </select>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-bold text-gray-400 uppercase tracking-widest">Your Message</label>
              <textarea 
                required
                rows={5}
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
        <p className="text-xs font-bold text-gray-400 uppercase tracking-widest">{title}</p>
        <p className="text-gray-900 font-semibold">{detail}</p>
      </div>
    </div>
  )
}
