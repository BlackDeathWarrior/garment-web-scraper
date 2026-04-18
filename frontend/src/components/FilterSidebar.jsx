import { FiX } from 'react-icons/fi'

const SORT_OPTIONS = [
  { value: 'default',       label: 'Relevance' },
  { value: 'price_asc',     label: 'Price: Low to High' },
  { value: 'price_desc',    label: 'Price: High to Low' },
  { value: 'rating_desc',   label: 'Rating: High to Low' },
  { value: 'discount_desc', label: 'Discount: High to Low' },
]

const GENDER_OPTIONS = ['Men', 'Women']

export default function FilterSidebar({
  filters,
  onFiltersChange,
  products,
  isOpen,
  onClose,
}) {
  const brands  = [...new Set(products.map((p) => p.brand).filter(Boolean))].sort()
  const colors  = [...new Set(products.map((p) => p.color).filter(Boolean))].sort()
  const sources = [...new Set(products.map((p) => p.source).filter(Boolean))].sort()

  const toggle = (key, value) => {
    const set = new Set(filters[key] ?? [])
    set.has(value) ? set.delete(value) : set.add(value)
    onFiltersChange({ ...filters, [key]: [...set] })
  }

  const clear = () =>
    onFiltersChange({ sources: [], brands: [], colors: [], genders: [], sort: 'default' })

  const activeCount =
    (filters.sources?.length ?? 0) +
    (filters.brands?.length  ?? 0) +
    (filters.colors?.length  ?? 0) +
    (filters.genders?.length ?? 0)

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-20 lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={`
          fixed lg:sticky top-0 lg:top-4 left-0 h-full lg:h-auto
          w-72 bg-white z-30 lg:z-auto border border-gray-200
          shadow-2xl lg:shadow-none rounded-r-2xl lg:rounded-xl
          p-5 overflow-y-auto
          transition-transform duration-300
          ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
          lg:self-start lg:max-h-[calc(100vh-5rem)]
        `}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-serif font-semibold text-xl text-gray-900">Filters</h2>
          <div className="flex items-center gap-2">
            {activeCount > 0 && (
              <button
                onClick={clear}
                className="text-sm text-maroon-700 hover:underline font-semibold"
              >
                Clear ({activeCount})
              </button>
            )}
            <button
              onClick={onClose}
              className="lg:hidden text-gray-400 hover:text-gray-700"
              aria-label="Close filters"
            >
              <FiX size={20} />
            </button>
          </div>
        </div>

        {/* Sort */}
        <Section title="Sort By">
          {SORT_OPTIONS.map((opt) => (
            <label
              key={opt.value}
              className="flex items-center gap-2 text-sm text-gray-800 cursor-pointer py-1 hover:text-maroon-700 font-medium"
            >
              <input
                type="radio"
                name="sort"
                value={opt.value}
                checked={filters.sort === opt.value}
                onChange={(e) =>
                  onFiltersChange({ ...filters, sort: e.target.value })
                }
                className="accent-maroon-700"
              />
              {opt.label}
            </label>
          ))}
        </Section>

        {/* Gender */}
        <Section title="Gender">
          {GENDER_OPTIONS.map((g) => (
            <CheckItem
              key={g}
              label={g}
              checked={filters.genders?.includes(g) ?? false}
              onChange={() => toggle('genders', g)}
            />
          ))}
        </Section>

        {/* Source */}
        {sources.length > 0 && (
          <Section title="Source">
            {sources.map((s) => (
              <CheckItem
                key={s}
                label={s.charAt(0).toUpperCase() + s.slice(1)}
                checked={filters.sources?.includes(s) ?? false}
                onChange={() => toggle('sources', s)}
              />
            ))}
          </Section>
        )}

        {/* Brand */}
        {brands.length > 0 && (
          <Section title="Brand">
            {brands.slice(0, 20).map((b) => (
              <CheckItem
                key={b}
                label={b}
                checked={filters.brands?.includes(b) ?? false}
                onChange={() => toggle('brands', b)}
              />
            ))}
          </Section>
        )}

        {/* Color */}
        {colors.length > 0 && (
          <Section title="Color">
            {colors.slice(0, 15).map((c) => (
              <CheckItem
                key={c}
                label={c}
                checked={filters.colors?.includes(c) ?? false}
                onChange={() => toggle('colors', c)}
              />
            ))}
          </Section>
        )}
      </aside>
    </>
  )
}

function Section({ title, children }) {
  return (
    <div className="mb-5">
      <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
        {title}
      </h3>
      {children}
      <div className="border-t border-gray-100 mt-3" />
    </div>
  )
}

function CheckItem({ label, checked, onChange }) {
  return (
    <label className="flex items-center gap-2 text-sm text-gray-800 cursor-pointer py-1 hover:text-maroon-700 font-medium">
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        className="accent-maroon-700 w-3.5 h-3.5 flex-shrink-0"
      />
      <span className="truncate">{label}</span>
    </label>
  )
}
