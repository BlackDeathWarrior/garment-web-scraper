import { Link } from 'react-router-dom'
import { FiSearch, FiSliders, FiMessageSquare } from 'react-icons/fi'

export default function Navbar({ search, onSearch, productCount, onMenuToggle }) {
  return (
    <header className="sticky top-0 z-40 bg-maroon-800 shadow-lg border-b border-maroon-900/50">
      <div className="max-w-screen-xl mx-auto px-4 py-3 flex items-center gap-4">
        <Link to="/" className="flex items-center gap-2.5 flex-shrink-0 group">
          <span className="text-gold-400 text-2xl leading-none select-none group-hover:scale-110 transition-transform">*</span>
          <div>
            <h1 className="font-serif text-white text-xl font-bold leading-none tracking-wide">
              Ethnic Threads
            </h1>
            <p className="text-gold-300 text-[10px] tracking-[0.18em] uppercase leading-none mt-0.5 font-semibold">
              Indian Wear
            </p>
          </div>
        </Link>

        <div className="flex-1 relative max-w-xl mx-auto">
          <FiSearch
            className="absolute left-3 top-1/2 -translate-y-1/2 text-white/70 pointer-events-none"
            size={16}
          />
          <input
            type="text"
            placeholder="Search kurtas, sarees, lehengas..."
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            className="w-full bg-white/20 border border-white/40 text-white placeholder-white/75
                       rounded-full py-2.5 pl-10 pr-4 text-sm font-medium
                       focus:outline-none focus:bg-white/25 focus:border-white/60
                       transition-all duration-200"
          />
        </div>

        <div className="flex items-center gap-3 flex-shrink-0">
          <Link 
            to="/contact" 
            className="text-white hover:text-gold-400 flex items-center gap-1.5 text-xs font-bold uppercase tracking-widest transition-colors mr-2"
          >
            <FiMessageSquare size={16} />
            <span className="hidden md:inline">Write to Us</span>
          </Link>
          {productCount !== undefined && productCount !== null && (
            <span className="text-white text-sm hidden sm:block font-semibold">
              {productCount.toLocaleString()} items
            </span>
          )}
          <button
            onClick={onMenuToggle}
            aria-label="Toggle filters"
            className="lg:hidden flex items-center gap-1.5 bg-white/20 hover:bg-white/30
                       text-white text-sm px-3 py-1.5 rounded-full transition-colors font-medium"
          >
            <FiSliders size={14} />
            <span>Filters</span>
          </button>
        </div>
      </div>
    </header>
  )
}
