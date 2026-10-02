import { useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { FiLock, FiMail } from 'react-icons/fi'
import { api } from '../lib/api'
import { setSession } from '../lib/auth'

/** Where to go after signing in: only ever a page of this site. */
export function nextPath(params, fallback = '/') {
  const next = params.get('next') || ''
  return next.startsWith('/') && !next.startsWith('//') ? next : fallback
}

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const [params] = useSearchParams()

  const handleLogin = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await api('/auth/login', { method: 'POST', body: { email, password } })
      setSession(data.token, data.user)
      navigate(data.user.role === 'admin' ? '/admin' : nextPath(params))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#faf8f5] flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-xl border border-gray-200 overflow-hidden">
        <div className="bg-maroon-700 p-8 text-center">
          <Link to="/" className="text-3xl font-bold text-white tracking-tight font-serif">
            Ethnic Threads
          </Link>
          <p className="text-maroon-100 mt-2">Sign in to continue</p>
        </div>

        <form onSubmit={handleLogin} className="p-8 space-y-6">
          {error && (
            <div role="alert" className="bg-red-50 border-l-4 border-red-500 p-4 text-red-700 text-sm">
              {error}
            </div>
          )}

          <div className="space-y-2">
            <label htmlFor="login-email" className="text-sm font-semibold text-gray-700 flex items-center gap-2">
              <FiMail size={16} className="text-gray-400" />
              Email
            </label>
            <input
              id="login-email"
              type="text"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-4 py-3 rounded-xl border border-gray-300 focus:ring-2 focus:ring-maroon-500 focus:border-transparent outline-none transition-all"
              placeholder="you@example.com"
            />
          </div>

          <div className="space-y-2">
            <label htmlFor="login-password" className="text-sm font-semibold text-gray-700 flex items-center gap-2">
              <FiLock size={16} className="text-gray-400" />
              Password
            </label>
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-3 rounded-xl border border-gray-300 focus:ring-2 focus:ring-maroon-500 focus:border-transparent outline-none transition-all"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-maroon-700 hover:bg-maroon-800 text-white font-bold py-3.5 rounded-xl transition-colors shadow-lg shadow-maroon-900/20 disabled:opacity-50"
          >
            {loading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>

        <div className="bg-gray-50 px-8 py-4 text-center border-t border-gray-100">
          <p className="text-sm text-gray-600">
            New to Ethnic Threads?{' '}
            <Link
              to={`/register${params.get('next') ? `?next=${encodeURIComponent(params.get('next'))}` : ''}`}
              className="text-maroon-700 font-bold hover:underline"
            >
              Create an account
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
