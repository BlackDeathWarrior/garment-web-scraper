import { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import { FiArrowDown, FiLogOut, FiAlertTriangle, FiClock } from 'react-icons/fi'
import { useNavigate } from 'react-router-dom'
import Navbar from '../components/Navbar'
import FilterSidebar from '../components/FilterSidebar'
import ProductGrid from '../components/ProductGrid'
import Pagination from '../components/Pagination'
import ScraperLog from '../components/ScraperLog'
import {
  DEFAULT_FILTERS,
  filterProducts,
  normalizeStoredFilters,
} from '../lib/productFilters'

const UI_PREFS_KEY = 'ethnic-threads-ui-prefs-v1'
const LAST_SCRAPE_KEY = 'ethnic-threads-last-manual-scrape'
const VALID_PER_PAGE_VALUES = new Set([0, 25, 50, 100])
const BOTTOM_THRESHOLD_PX = 120
const MANUAL_COOLDOWN_MS = 5 * 60 * 1000

function loadStoredPrefs() {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(UI_PREFS_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function normalizeStoredPerPage(value) {
  const num = Number(value)
  return VALID_PER_PAGE_VALUES.has(num) ? num : 25
}

export default function Home() {
  const storedPrefs = useMemo(() => loadStoredPrefs(), [])
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState(() =>
    typeof storedPrefs.search === 'string' ? storedPrefs.search : ''
  )
  const [filters, setFilters] = useState(() =>
    normalizeStoredFilters(storedPrefs.filters ?? DEFAULT_FILTERS)
  )
  const [lastUpdatedAt, setLastUpdatedAt] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [perPage, setPerPage] = useState(() =>
    normalizeStoredPerPage(storedPrefs.perPage)
  )
  const [page, setPage] = useState(1)
  const [scrapeHint, setScrapeHint] = useState('Admin Session Active')
  const [scrapeBusy, setScrapeBusy] = useState(false)
  const [scrapeStatus, setScrapeStatus] = useState({ running: false, pid: null })
  const [cooldownRemaining, setCooldownRemaining] = useState(0)
  
  const navigate = useNavigate()
  const hasLoadedSuccessfully = useRef(false)
  const scrapeRequestInFlight = useRef(false)

  // Cooldown logic
  useEffect(() => {
    const checkCooldown = () => {
      const lastScrape = Number(localStorage.getItem(LAST_SCRAPE_KEY) || 0)
      const now = Date.now()
      const diff = now - lastScrape
      if (diff < MANUAL_COOLDOWN_MS) {
        setCooldownRemaining(Math.ceil((MANUAL_COOLDOWN_MS - diff) / 1000))
      } else {
        setCooldownRemaining(0)
      }
    }
    checkCooldown()
    const timer = setInterval(checkCooldown, 1000)
    return () => clearInterval(timer)
  }, [])

  const handleLogout = () => {
    localStorage.removeItem('scraper_auth_token')
    navigate('/login')
  }

  const fetchProducts = useCallback(async (initialLoad = false) => {
    try {
      const localUrl = `/products.json?v=${Date.now()}`
      const baseUrl = import.meta.env.VITE_API_BASE || ''
      const apiUrl = baseUrl ? `${baseUrl}/products` : null

      let response = await fetch(localUrl, { cache: 'no-store' })
      
      if (apiUrl) {
        try {
          const apiRes = await fetch(apiUrl, { cache: 'no-store' })
          if (apiRes.ok) response = apiRes
        } catch (apiErr) {
          console.warn('API fetch failed, staying with local data', apiErr)
        }
      }

      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const payload = await response.json()
      const incoming = Array.isArray(payload) ? payload : []
      
      setProducts(incoming)
      setLastUpdatedAt(new Date())
      setError(null)
      hasLoadedSuccessfully.current = true
    } catch (err) {
      if (initialLoad || !hasLoadedSuccessfully.current) {
        setError(err.message || 'Failed to load products')
      }
    } finally {
      if (initialLoad) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchProducts(true)
    const intervalId = setInterval(() => {
      void fetchProducts(false)
    }, 60_000 * 5)
    return () => clearInterval(intervalId)
  }, [fetchProducts])

  useEffect(() => {
    setPage(1)
  }, [search, filters, perPage])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const payload = { search, filters, perPage }
    try {
      window.localStorage.setItem(UI_PREFS_KEY, JSON.stringify(payload))
    } catch {}
  }, [search, filters, perPage])

  const requestScrapeCycle = async (reason = 'manual') => {
    if (cooldownRemaining > 0 && reason === 'manual') return
    if (scrapeRequestInFlight.current) return
    
    scrapeRequestInFlight.current = true
    setScrapeBusy(true)
    setScrapeHint('Requesting scrape...')

    try {
      const baseUrl = import.meta.env.VITE_API_BASE || ''
      const url = baseUrl ? `${baseUrl}/api/scrape-cycle` : '/api/scrape-cycle'

      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
      })
      
      if (response.ok) {
        localStorage.setItem(LAST_SCRAPE_KEY, Date.now().toString())
        setScrapeHint('Scrape started successfully')
        return { ok: true }
      } else {
        const errData = await response.json().catch(() => ({}))
        setScrapeHint(`Failed: ${errData.error || response.status}`)
        return { ok: false, reason: 'error', status: response.status }
      }
    } catch (err) {
      setScrapeHint('Connection error - is scraper running?')
      return { ok: false, reason: 'network-error' }
    } finally {
      scrapeRequestInFlight.current = false
      setScrapeBusy(false)
    }
  }

  const filtered = useMemo(
    () => filterProducts(products, search, filters),
    [products, search, filters]
  )

  const paged = useMemo(() => {
    if (perPage === 0) return filtered
    const start = (page - 1) * perPage
    return filtered.slice(start, start + perPage)
  }, [filtered, perPage, page])

  const formatCooldown = (seconds) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  return (
    <div className="min-h-screen bg-[#faf8f5]">
      <div className="bg-maroon-900 text-white py-1 px-4 flex justify-between items-center text-[10px] uppercase tracking-widest font-bold">
        <span>Admin Mode: scraper_admin</span>
        <button onClick={handleLogout} className="flex items-center gap-1 hover:text-amber-400 transition-colors">
          <FiLogOut size={10} /> Logout
        </button>
      </div>
      
      <Navbar
        search={search}
        onSearch={setSearch}
        productCount={filtered.length}
        onMenuToggle={() => setSidebarOpen((o) => !o)}
      />

      <div className="max-w-screen-xl mx-auto px-4 py-6 flex gap-6 items-start">
        <FilterSidebar
          filters={filters}
          onFiltersChange={setFilters}
          products={products}
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
        />

        <main className="flex-1 min-w-0">
          {!loading && !error && (
            <p className="text-sm text-gray-600 mb-4 font-medium">
              Showing{' '}
              <span className="font-semibold text-gray-900">
                {filtered.length.toLocaleString('en-IN')}
              </span>{' '}
              of {products.length.toLocaleString('en-IN')} products
              {lastUpdatedAt && (
                <span className="ml-2 text-xs text-gray-500">
                  | Last Sync {lastUpdatedAt.toLocaleTimeString('en-IN')}
                </span>
              )}
            </p>
          )}
          
          <ProductGrid products={paged} loading={loading} error={error} />
          
          <Pagination
            total={filtered.length}
            perPage={perPage}
            page={page}
            onPerPageChange={setPerPage}
            onPageChange={setPage}
          />

          <section className="mt-8 p-6 rounded-2xl bg-white border border-gray-200 shadow-sm overflow-hidden relative">
            <div className="flex flex-col md:flex-row gap-6 items-start justify-between">
              <div className="flex-1">
                <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                  Admin Controls
                </h2>
                <div className="mt-2 p-3 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-3">
                  <FiAlertTriangle className="text-amber-600 mt-0.5 shrink-0" size={18} />
                  <p className="text-xs text-amber-800 leading-relaxed">
                    <strong>Warning:</strong> Avoid clicking too frequently. Rapid requests to e-commerce sites can get your 
                    Cloud IP blocked permanently. Please use manual triggers only when necessary.
                  </p>
                </div>
              </div>

              <div className="flex flex-col items-center md:items-end gap-3 shrink-0">
                <button
                  onClick={() => requestScrapeCycle('manual')}
                  disabled={scrapeBusy || scrapeStatus.running || cooldownRemaining > 0}
                  className="bg-maroon-700 hover:bg-maroon-800 text-white px-8 py-3 rounded-xl font-bold text-sm disabled:bg-gray-200 disabled:text-gray-400 transition-all shadow-lg shadow-maroon-900/10 flex items-center gap-2 min-w-[200px] justify-center"
                >
                  {cooldownRemaining > 0 ? (
                    <>
                      <FiClock size={16} /> Wait {formatCooldown(cooldownRemaining)}
                    </>
                  ) : (
                    scrapeBusy ? 'Processing...' : 'Trigger Full Scrape'
                  )}
                </button>
                <p className="text-[11px] font-medium text-gray-400">
                  {scrapeHint}
                </p>
              </div>
            </div>
          </section>
        </main>
      </div>

      <ScraperLog onRunScrape={() => requestScrapeCycle('manual')} />
    </div>
  )
}
