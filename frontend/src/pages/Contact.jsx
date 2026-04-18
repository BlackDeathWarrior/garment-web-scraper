import { FiMail, FiMessageSquare, FiSend, FiShield, FiUser } from 'react-icons/fi'
import Navbar from '../components/Navbar'

export default function Contact() {
  // Standard HTML form submission is the only way to use direct email addresses 
  // with Formspree without a pre-generated ID.
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

          <form 
            action="https://formspree.io/prithvijay2006@gmail.com" 
            method="POST"
            className="bg-white p-8 rounded-3xl shadow-xl shadow-maroon-900/5 border border-gray-100 space-y-6"
          >
            <div className="grid grid-cols-1 gap-6">
              <div className="space-y-2">
                <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Your Name</label>
                <div className="relative">
                  <FiUser className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400" />
                  <input type="text" name="name" required className="w-full pl-11 pr-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-maroon-500 outline-none bg-gray-50 text-sm" placeholder="John Doe" />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Email Address</label>
                <div className="relative">
                  <FiMail className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400" />
                  <input type="email" name="_replyto" required className="w-full pl-11 pr-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-maroon-500 outline-none bg-gray-50 text-sm" placeholder="john@example.com" />
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Subject</label>
              <select name="_subject" className="w-full px-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-maroon-500 outline-none bg-gray-50 text-sm font-medium">
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
              className="w-full bg-maroon-700 hover:bg-maroon-800 text-white font-bold py-4 rounded-xl transition-all shadow-lg shadow-maroon-900/20 flex items-center justify-center gap-2"
            >
              <FiSend /> Send Message
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
