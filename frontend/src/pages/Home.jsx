import { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import { FiLayout } from 'react-icons/fi'
import Navbar from '../components/Navbar'
import FilterSidebar from '../components/FilterSidebar'
import ProductGrid from '../components/ProductGrid'
import Pagination from '../components/Pagination'
import ProductModal from '../components/ProductModal'
import { DEFAULT_FILTERS, filterProducts, normalizeStoredFilters } from '../lib/productFilters'
import { productContext, setSupportContext } from '../lib/support'

const UI_PREFS_KEY = 'ethnic-threads-ui-prefs-v1'
const VALID_PER_PAGE_VALUES = new Set([0, 25, 50, 100])

const PER_PAGE_OPTIONS = [
  { value: 25, label: '25' },
  { value: 50, label: '50' },
  { value: 100, label: '100' },
  { value: 0, label: 'All' },
]

function loadStoredPrefs() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(UI_PREFS_KEY) || '{}')
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function normalizeStoredPerPage(value) {
  const num = Number(value)
  return VALID_PER_PAGE_VALUES.has(num) ? num : 25
}

/** The shop window: every product, searchable and filterable. Anyone can browse. */
export default function Home() {
  const storedPrefs = useMemo(() => loadStoredPrefs(), [])
  const [products, setProducts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState(() => (typeof storedPrefs.search === 'string' ? storedPrefs.search : ''))
  const [filters, setFilters] = useState(() => normalizeStoredFilters(storedPrefs.filters ?? DEFAULT_FILTERS))
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [perPage, setPerPage] = useState(() => normalizeStoredPerPage(storedPrefs.perPage))
  const [page, setPage] = useState(1)
  const [selectedProduct, setSelectedProduct] = useState(null)
  const hasLoadedSuccessfully = useRef(false)

  const fetchProducts = useCallback(async () => {
    try {
      const response = await fetch(`/products.json?v=${Date.now()}`, { cache: 'no-store' })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const payload = await response.json()
      setProducts(Array.isArray(payload) ? payload : [])
      setError(null)
      hasLoadedSuccessfully.current = true
    } catch (err) {
      if (!hasLoadedSuccessfully.current) setError(err.message || 'Failed to load products')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchProducts()
  }, [fetchProducts])

  useEffect(() => {
    setPage(1)
  }, [search, filters, perPage])

  // The chat widget tells support which product the visitor has open.
  useEffect(() => {
    setSupportContext({ page: 'shop', ...productContext(selectedProduct) })
    return () => setSupportContext({})
  }, [selectedProduct])

  useEffect(() => {
    try {
      window.localStorage.setItem(UI_PREFS_KEY, JSON.stringify({ search, filters, perPage }))
    } catch {}
  }, [search, filters, perPage])

  const filtered = useMemo(() => filterProducts(products, search, filters), [products, search, filters])

  const paged = useMemo(() => {
    if (perPage === 0) return filtered
    const start = (page - 1) * perPage
    return filtered.slice(start, start + perPage)
  }, [filtered, perPage, page])

  return (
    <div className="min-h-screen bg-[#faf8f5]">
      <Navbar search={search} onSearch={setSearch} onMenuToggle={() => setSidebarOpen((o) => !o)} />

      <div className="max-w-screen-xl mx-auto px-4 py-6 flex gap-6 items-start">
        <div className="w-64 shrink-0 hidden lg:block">
          {!loading && !error && (
            <>
              <div className="mb-6 px-1">
                <p className="text-sm text-gray-600 font-medium">
                  Showing{' '}
                  <span className="font-semibold text-gray-900">{filtered.length.toLocaleString('en-IN')}</span> of{' '}
                  {products.length.toLocaleString('en-IN')} products
                </p>
              </div>

              <FilterSidebar
                filters={filters}
                onFiltersChange={setFilters}
                products={products}
                isOpen={sidebarOpen}
                onClose={() => setSidebarOpen(false)}
              />

              <div className="mt-8 px-1">
                <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest flex items-center gap-1.5 mb-3">
                  <FiLayout size={12} className="text-maroon-700" /> Items per page
                </p>
                <div className="grid grid-cols-2 gap-2">
                  {PER_PAGE_OPTIONS.map(({ value, label }) => (
                    <button
                      key={value}
                      onClick={() => setPerPage(value)}
                      className={`px-3 py-2 rounded-xl text-xs font-bold transition-all border ${
                        perPage === value
                          ? 'bg-maroon-700 text-white border-maroon-700 shadow-md'
                          : 'bg-white text-gray-500 border-gray-200 hover:border-maroon-300'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>

        <div className="lg:hidden">
          <FilterSidebar
            filters={filters}
            onFiltersChange={setFilters}
            products={products}
            isOpen={sidebarOpen}
            onClose={() => setSidebarOpen(false)}
          />
        </div>

        <main className="flex-1 min-w-0">
          <ProductGrid products={paged} loading={loading} error={error} onProductClick={setSelectedProduct} />
          <Pagination total={filtered.length} perPage={perPage} page={page} onPageChange={setPage} />
        </main>
      </div>

      <ProductModal product={selectedProduct} onClose={() => setSelectedProduct(null)} />
    </div>
  )
}
