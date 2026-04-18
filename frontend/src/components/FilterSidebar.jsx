import { useState } from 'react'
import { FiX, FiSearch, FiFilter } from 'react-icons/fi'

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
  const [brandSearch, setBrandSearch] = useState('')

  const brands  = [...new Set(products.map((p) => p.brand).filter(Boolean))].sort()
  const colors  = [...new Set(products.map((p) => p.color).filter(Boolean))].sort()
  const sources = [...new Set(products.map((p) => p.source).filter(Boolean))].sort()

  const filteredBrands = brands.filter(b => 
    b.toLowerCase().includes(brandSearch.toLowerCase())
  )

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
        <div className="flex items-center justify-between mb-5 pb-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <FiFilter className="text-maroon-700" size={18} />
            <h2 className="font-bold text-lg text-gray-900">Filters</h2>
          </div>
          <div className="flex items-center gap-2">
            {activeCount > 0 && (
              <button
                onClick={clear}
                className="text-xs bg-maroon-50 text-maroon-700 px-2 py-1 rounded-md hover:bg-maroon-100 transition-colors font-bold"
              >
                Clear All
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
          <div className="grid gap-1">
            {SORT_OPTIONS.map((opt) => (
              <label
                key={opt.value}
                htmlFor={`sort-${opt.value}`}
                className={`flex items-center gap-2.5 text-sm cursor-pointer py-2 px-3 rounded-xl transition-all font-bold border
                  ${filters.sort === opt.value 
                    ? 'bg-maroon-700 text-white border-maroon-700 shadow-md ring-2 ring-maroon-100' 
                    : 'text-gray-600 bg-white border-gray-100 hover:bg-gray-50'}`}
              >
                <input
                  type="radio"
                  id={`sort-${opt.value}`}
                  name="sort"
                  value={opt.value}
                  checked={filters.sort === opt.value}
                  onChange={() => onFiltersChange({ ...filters, sort: opt.value })}
                  className="accent-white w-4 h-4"
                />
                {opt.label}
              </label>
            ))}
          </div>
        </Section>

        {/* Gender */}
        <Section title="Gender">
          <div className="grid gap-1">
            {GENDER_OPTIONS.map((g) => (
              <CheckItem
                key={g}
                id={`gender-${g}`}
                label={g}
                checked={filters.genders?.includes(g) ?? false}
                onChange={() => toggle('genders', g)}
              />
            ))}
          </div>
        </Section>

        {/* Source */}
        {sources.length > 0 && (
          <Section title="Source">
            <div className="grid gap-1">
              {sources.map((s) => (
                <CheckItem
                  key={s}
                  id={`source-${s}`}
                  label={s.charAt(0).toUpperCase() + s.slice(1)}
                  checked={filters.sources?.includes(s) ?? false}
                  onChange={() => toggle('sources', s)}
                />
              ))}
            </div>
          </Section>
        )}

        {/* Brand - SEARCHABLE */}
        <Section title="Brand">
          <div className="relative mb-3">
            <FiSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={14} />
            <input
              type="text"
              placeholder="Search brands..."
              value={brandSearch}
              onChange={(e) => setBrandSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-xs focus:ring-2 focus:ring-maroon-500 focus:border-transparent outline-none transition-all"
            />
          </div>
          <div className="grid gap-1 max-h-48 overflow-y-auto pr-1 custom-scrollbar">
            {filteredBrands.length > 0 ? (
              filteredBrands.map((b) => (
                <CheckItem
                  key={b}
                  id={`brand-${b}`}
                  label={b}
                  checked={filters.brands?.includes(b) ?? false}
                  onChange={() => toggle('brands', b)}
                />
              ))
            ) : (
              <p className="text-[11px] text-gray-400 italic py-2 text-center">No brands found</p>
            )}
          </div>
        </Section>

        {/* Color */}
        {colors.length > 0 && (
          <Section title="Color">
            <div className="grid gap-1 max-h-40 overflow-y-auto pr-1 custom-scrollbar">
              {colors.map((c) => (
                <CheckItem
                  key={c}
                  id={`color-${c}`}
                  label={c}
                  checked={filters.colors?.includes(c) ?? false}
                  onChange={() => toggle('colors', c)}
                />
              ))}
            </div>
          </Section>
        )}
      </aside>
    </>
  )
}

function Section({ title, children }) {
  return (
    <div className="mb-6">
      <h3 className="text-[10px] font-bold text-gray-400 uppercase tracking-[2px] mb-3">
        {title}
      </h3>
      {children}
    </div>
  )
}

function CheckItem({ id, label, checked, onChange }) {
  return (
    <label 
      htmlFor={id}
      className={`
      flex items-center gap-2.5 text-sm cursor-pointer py-2 px-3 rounded-xl transition-all font-bold border
      ${checked 
        ? 'bg-maroon-700 text-white border-maroon-700 shadow-md ring-2 ring-maroon-100' 
        : 'text-gray-600 bg-white border-gray-100 hover:bg-gray-50 hover:border-gray-200'}
    `}>
      <input
        type="checkbox"
        id={id}
        checked={checked}
        onChange={onChange}
        className="accent-white w-4 h-4 flex-shrink-0"
      />
      <span className="truncate">{label}</span>
    </label>
  )
}
