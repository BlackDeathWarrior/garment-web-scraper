import { useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { FiMail, FiLock, FiUser, FiArrowRight } from 'react-icons/fi'
import { api } from '../lib/api'
import { setSession } from '../lib/auth'
import { nextPath } from './Login'

export default function Register() {
  const [form, setForm] = useState({ name: '', email: '', password: '', confirm: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  const handleRegister = async (e) => {
    e.preventDefault()
    setError('')
    if (form.password.length < 8) return setError('Choose a password of at least 8 characters.')
    if (form.password !== form.confirm) return setError('The two passwords do not match.')
    setLoading(true)
    try {
      const data = await api('/auth/register', {
        method: 'POST',
        body: { name: form.name, email: form.email, password: form.password },
      })
      setSession(data.token, data.user)
      navigate(nextPath(params))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const field =
    'w-full px-4 py-3 rounded-xl border border-gray-300 focus:ring-2 focus:ring-maroon-500 focus:border-transparent outline-none transition-all'
  const label = 'text-sm font-semibold text-gray-700 flex items-center gap-2'

  return (
    <div className="min-h-screen bg-[#faf8f5] flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-xl border border-gray-200 overflow-hidden">
        <div className="bg-maroon-700 p-8 text-center">
          <h1 className="text-3xl font-bold text-white tracking-tight">Create Account</h1>
          <p className="text-maroon-100 mt-2">Shop Indian wear at Ethnic Threads</p>
        </div>

        <form onSubmit={handleRegister} className="p-8 space-y-5">
          {error && (
            <div role="alert" className="bg-red-50 border-l-4 border-red-500 p-4 text-red-700 text-sm">
              {error}
            </div>
          )}

          <div className="space-y-2">
            <label htmlFor="register-name" className={label}>
              <FiUser size={16} className="text-gray-400" /> Your name
            </label>
            <input id="register-name" type="text" autoComplete="name" required value={form.name} onChange={set('name')} className={field} />
          </div>
          <div className="space-y-2">
            <label htmlFor="register-email" className={label}>
              <FiMail size={16} className="text-gray-400" /> Email
            </label>
            <input
              id="register-email"
              type="email"
              autoComplete="email"
              required
              value={form.email}
              onChange={set('email')}
              className={field}
              placeholder="you@example.com"
            />
          </div>
          <div className="space-y-2">
            <label htmlFor="register-password" className={label}>
              <FiLock size={16} className="text-gray-400" /> Password
            </label>
            <input
              id="register-password"
              type="password"
              autoComplete="new-password"
              required
              value={form.password}
              onChange={set('password')}
              className={field}
            />
            <p className="text-xs text-gray-500">At least 8 characters.</p>
          </div>
          <div className="space-y-2">
            <label htmlFor="register-confirm" className={label}>
              <FiLock size={16} className="text-gray-400" /> Password again
            </label>
            <input
              id="register-confirm"
              type="password"
              autoComplete="new-password"
              required
              value={form.confirm}
              onChange={set('confirm')}
              className={field}
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-maroon-700 hover:bg-maroon-800 text-white font-bold py-3.5 rounded-xl transition-all shadow-lg shadow-maroon-900/20 disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? 'Creating your account...' : <>Create account <FiArrowRight /></>}
          </button>
        </form>

        <div className="bg-gray-50 px-8 py-4 text-center border-t border-gray-100">
          <p className="text-sm text-gray-600">
            Already have an account?{' '}
            <Link
              to={`/login${params.get('next') ? `?next=${encodeURIComponent(params.get('next'))}` : ''}`}
              className="text-maroon-700 font-bold hover:underline"
            >
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
