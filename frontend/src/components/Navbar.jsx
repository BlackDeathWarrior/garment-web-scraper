import { Link, useNavigate } from 'react-router-dom'
import { FiSearch, FiSliders, FiX, FiShoppingCart, FiPackage, FiInbox, FiUser, FiLogOut, FiSettings } from 'react-icons/fi'
import { clearSession, isAdmin, isShopper, useUser } from '../lib/auth'
import { cartCount, useCart } from '../lib/cart'

const link =
  'text-white hover:text-gold-400 flex items-center gap-1.5 text-xs font-bold uppercase tracking-widest transition-colors'

export default function Navbar({ search, onSearch, onMenuToggle }) {
  const user = useUser()
  const count = cartCount(useCart())
  const navigate = useNavigate()

  const signOut = () => {
    clearSession()
    navigate('/')
  }

  return (
    <header className="sticky top-0 z-40 bg-maroon-800 shadow-lg border-b border-maroon-900/50">
      <div className="max-w-screen-xl mx-auto px-4 py-3 flex items-center gap-2 sm:gap-4">
        <Link to="/" className="flex items-center gap-2.5 flex-shrink-0 group">
          <span className="text-gold-400 text-2xl leading-none select-none group-hover:scale-110 transition-transform">*</span>
          <div>
            <p className="font-serif text-white text-xl font-bold leading-none tracking-wide">Ethnic Threads</p>
            <p className="text-gold-300 text-[10px] tracking-[0.18em] uppercase leading-none mt-0.5 font-semibold">
              Indian Wear
            </p>
          </div>
        </Link>

        {onSearch ? (
          <div className="flex-1 min-w-0 relative max-w-xl mx-auto">
            <FiSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-white/70 pointer-events-none" size={16} />
            <input
              type="text"
              aria-label="Search products"
              placeholder="Search kurtas, sarees, lehengas..."
              value={search}
              onChange={(e) => onSearch(e.target.value)}
              className="w-full bg-white/20 border border-white/40 text-white placeholder-white/75
                         rounded-full py-2.5 pl-10 pr-10 text-sm font-medium
                         focus:outline-none focus:bg-white/25 focus:border-white/60
                         transition-all duration-200"
            />
            {search && (
              <button
                onClick={() => onSearch('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-white/60 hover:text-white transition-colors"
                aria-label="Clear search"
              >
                <FiX size={18} />
              </button>
            )}
          </div>
        ) : (
          <div className="flex-1" />
        )}

        <nav className="flex items-center gap-3 sm:gap-4 flex-shrink-0" aria-label="Account">
          {isAdmin(user) && (
            <Link to="/admin" className={link}>
              <FiSettings size={16} />
              <span className="hidden md:inline">Operations</span>
            </Link>
          )}
          {isShopper(user) && (
            <Link to="/orders" className={link}>
              <FiPackage size={16} />
              <span className="hidden md:inline">Orders</span>
            </Link>
          )}
          <Link to="/requests" className={link} aria-label="Help">
            <FiInbox size={16} />
            <span className="hidden md:inline">Help</span>
          </Link>
          {user ? (
            <button onClick={signOut} className={link} aria-label={`Sign out ${user.name}`}>
              <FiLogOut size={16} />
              <span className="hidden lg:inline max-w-[9rem] truncate">{user.name.split(' ')[0]}</span>
            </button>
          ) : (
            <Link to="/login" className={link}>
              <FiUser size={16} />
              <span className="hidden md:inline">Sign in</span>
            </Link>
          )}
          <Link to="/cart" className={`${link} relative`} aria-label={`Cart, ${count} item${count === 1 ? '' : 's'}`}>
            <FiShoppingCart size={18} />
            {count > 0 && (
              <span
                data-testid="cart-count"
                className="absolute -top-2 -right-2.5 bg-gold-400 text-maroon-900 text-[10px] font-bold rounded-full min-w-[18px] h-[18px] px-1 flex items-center justify-center"
              >
                {count}
              </span>
            )}
          </Link>
          {onMenuToggle && (
            <button
              onClick={onMenuToggle}
              aria-label="Toggle filters"
              className="lg:hidden flex items-center gap-1.5 bg-white/20 hover:bg-white/30
                         text-white text-sm px-3 py-1.5 rounded-full transition-colors font-medium"
            >
              <FiSliders size={14} />
            </button>
          )}
        </nav>
      </div>
    </header>
  )
}
