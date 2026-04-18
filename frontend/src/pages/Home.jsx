import { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import { FiArrowDown, FiLogOut } from 'react-icons/fi'
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
const VALID_PER_PAGE_VALUES = new Set([0, 25, 50, 100])
const BOTTOM_THRESHOLD_PX = 120
const SCRAPE_TRIGGER_COOLDOWN_MS = 3 * 60 * 1000

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
  const [showScrollBtn, setShowScrollBtn] = useState(false)
  const [scrapeHint, setScrapeHint] = useState('Admin Session Active')
  const [scrapeBusy, setScrapeBusy] = useState(false)
  const [waitingForMoreProducts, setWaitingForMoreProducts] = useState(false)
  const [scrapeStatus, setScrapeStatus] = useState({ running: false, pid: null })
  
  const navigate = useNavigate()
  const hasLoadedSuccessfully = useRef(false)
  const lastScrapeTriggerAt = useRef(0)
  const scrapeRequestInFlight = useRef(false)

  const handleLogout = () => {
    localStorage.removeItem('scraper_auth_token')
    navigate('/login')
  }

  const fetchProducts = useCallback(async (initialLoad = false) => {
    try {
      // In production, this would be an AWS API Gateway call:
      // const response = await fetch(`${import.meta.env.VITE_API_BASE}/products?page=${page}&perPage=${perPage}...`)
      const response = await fetch(`/products.json?v=${Date.now()}`, {
        cache: 'no-store',
      })
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
    // Reduce polling frequency significantly to stop lag from re-parsing massive JSON
    const intervalId = setInterval(() => {
      void fetchProducts(false)
    }, 60_000 * 5) // Poll every 5 minutes instead of 20 seconds

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
    const now = Date.now()
    if (reason === 'scroll' && now - lastScrapeTriggerAt.current < SCRAPE_TRIGGER_COOLDOWN_MS) return
    if (scrapeRequestInFlight.current) return
    scrapeRequestInFlight.current = true
    setScrapeBusy(true)

    try {
      const response = await fetch('/api/scrape-cycle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
      })
      if (response.ok) {
        lastScrapeTriggerAt.current = now
        setScrapeHint(reason === 'scroll' ? 'Auto-scrape triggered' : 'Scrape started')
        if (reason === 'scroll') setWaitingForMoreProducts(true)
      }
    } catch {
      setScrapeHint('Scraper trigger failed')
    } finally {
      scrapeRequestInFlight.current = false
      setScrapeBusy(false)
    }
  }

  // Memoize filtered results to prevent lag during re-renders
  const filtered = useMemo(
    () => filterProducts(products, search, filters),
    [products, search, filters]
  )

  const paged = useMemo(() => {
    if (perPage === 0) return filtered
    const start = (page - 1) * perPage
    return filtered.slice(start, start + perPage)
  }, [filtered, perPage, page])

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

          <section className="mt-8 p-6 rounded-2xl bg-white border border-gray-200 shadow-sm">
            <h2 className="text-lg font-bold text-gray-900">Admin Controls</h2>
            <div className="mt-4 flex flex-col sm:flex-row gap-4 items-center justify-between">
              <p className="text-sm text-gray-600">
                {scrapeHint} | Status: {scrapeStatus.running ? 'Scraping...' : 'Idle'}
              </p>
              <button
                onClick={() => requestScrapeCycle('manual')}
                disabled={scrapeBusy || scrapeStatus.running}
                className="bg-maroon-700 hover:bg-maroon-800 text-white px-6 py-2.5 rounded-xl font-semibold text-sm disabled:opacity-50 transition-all shadow-md"
              >
                {scrapeBusy || scrapeStatus.running ? 'Processing...' : 'Trigger Full Scrape'}
              </button>
            </div>
          </section>
        </main>
      </div>

      <ScraperLog onRunScrape={() => requestScrapeCycle('manual')} />
    </div>
  )
}
