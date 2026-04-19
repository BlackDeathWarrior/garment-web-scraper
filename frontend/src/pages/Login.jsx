import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { FiLock, FiUser, FiKey } from 'react-icons/fi'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [otp, setOtp] = useState('')
  const [step, setStep] = useState(1) // 1: credentials, 2: otp
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleLogin = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const baseUrl = import.meta.env.VITE_API_BASE || ''
      
      if (step === 1) {
        // Step 1: Send credentials to get OTP
        const res = await fetch(`${baseUrl}/api/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password })
        })
        const data = await res.json()
        
        if (data.ok && data.require_otp) {
          setStep(2)
        } else {
          setError(data.reason === 'invalid-credentials' ? 'Invalid username or password' : 'Login failed')
        }
      } else {
        // Step 2: Verify OTP
        const res = await fetch(`${baseUrl}/api/auth/verify`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, otp })
        })
        const data = await res.json()
        
        if (data.ok && data.token) {
          localStorage.setItem('scraper_auth_token', data.token)
          localStorage.setItem('scraper_user_role', 'admin')
          navigate('/')
        } else {
          setError('Invalid or expired OTP')
        }
      }
    } catch (err) {
      setError('An error occurred during authentication')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#faf8f5] flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-xl border border-gray-200 overflow-hidden">
        <div className="bg-maroon-700 p-8 text-center">
          <h1 className="text-3xl font-bold text-white tracking-tight">Ethnic Threads</h1>
          <p className="text-maroon-100 mt-2">
            {step === 1 ? 'Login to Continue' : 'Verify One-Time Password'}
          </p>
        </div>
        
        <form onSubmit={handleLogin} className="p-8 space-y-6">
          {error && (
            <div className="bg-red-50 border-l-4 border-red-500 p-4 text-red-700 text-sm">
              {error}
            </div>
          )}
          
          {step === 1 ? (
            <>
              <div className="space-y-2">
                <label className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                  <FiUser size={16} className="text-gray-400" />
                  Username
                </label>
                <input
                  type="text"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full px-4 py-3 rounded-xl border border-gray-300 focus:ring-2 focus:ring-maroon-500 focus:border-transparent outline-none transition-all"
                  placeholder="Enter username"
                />
              </div>
              
              <div className="space-y-2">
                <label className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                  <FiLock size={16} className="text-gray-400" />
                  Password
                </label>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-3 rounded-xl border border-gray-300 focus:ring-2 focus:ring-maroon-500 focus:border-transparent outline-none transition-all"
                  placeholder="••••••••"
                />
              </div>
            </>
          ) : (
            <div className="space-y-2">
              <label className="text-sm font-semibold text-gray-700 flex items-center gap-2">
                <FiKey size={16} className="text-gray-400" />
                OTP Code
              </label>
              <input
                type="text"
                required
                maxLength={6}
                value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
                className="w-full px-4 py-3 rounded-xl border border-gray-300 focus:ring-2 focus:ring-maroon-500 focus:border-transparent outline-none transition-all text-center text-2xl tracking-[0.5em] font-bold"
                placeholder="000000"
                autoFocus
              />
              <p className="text-xs text-gray-500 text-center mt-2">
                Check your email for a 6-digit verification code.
              </p>
            </div>
          )}
          
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-maroon-700 hover:bg-maroon-800 text-white font-bold py-3.5 rounded-xl transition-colors shadow-lg shadow-maroon-900/20 disabled:opacity-50"
          >
            {loading ? 'Authenticating...' : (step === 1 ? 'Sign In' : 'Verify OTP')}
          </button>

          {step === 2 && (
            <button
              type="button"
              onClick={() => { setStep(1); setOtp(''); setError(''); }}
              className="w-full text-maroon-700 text-sm font-semibold hover:underline"
            >
              Back to Login
            </button>
          )}
        </form>
        
        <div className="bg-gray-50 px-8 py-4 text-center border-t border-gray-100">
          <p className="text-sm text-gray-600">
            Don't have an account?{' '}
            <Link to="/register" className="text-maroon-700 font-bold hover:underline">
              Register Now
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
