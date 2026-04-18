const PER_PAGE_OPTIONS = [
  { value: 25, label: '25' },
  { value: 50, label: '50' },
  { value: 100, label: '100' },
  { value: 0, label: 'All' },
]

function buildPageNumbers(current, total) {
  if (total <= 9) return Array.from({ length: total }, (_, i) => i + 1)

  const keep = new Set([1, 2, total - 1, total])
  for (let i = Math.max(1, current - 1); i <= Math.min(total, current + 1); i += 1) {
    keep.add(i)
  }

  const sorted = [...keep].sort((a, b) => a - b)
  const result = []
  let prev = 0
  for (const p of sorted) {
    if (p - prev > 1) result.push('...')
    result.push(p)
    prev = p
  }
  return result
}

export default function Pagination({ total, perPage, page, onPerPageChange, onPageChange }) {
  if (total === 0) return null

  const totalPages = perPage === 0 ? 1 : Math.ceil(total / perPage)
  const pageNumbers = buildPageNumbers(page, totalPages)

  const start = perPage === 0 ? 1 : (page - 1) * perPage + 1
  const end = perPage === 0 ? total : Math.min(page * perPage, total)

  return (
    <div className="mt-8 flex flex-col items-center gap-4 select-none">
      <div className="flex items-center gap-2 flex-wrap justify-center">
        <span className="text-sm text-gray-500 font-medium">Show per page:</span>
        <div className="flex gap-1.5">
          {PER_PAGE_OPTIONS.map(({ value, label }) => (
            <button
              key={value}
              onClick={() => {
                onPerPageChange(value)
                onPageChange(1)
              }}
              className={`px-3.5 py-1.5 rounded-lg text-sm font-semibold transition-colors ${
                perPage === value
                  ? 'bg-maroon-700 text-white shadow-sm'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <span className="text-sm text-gray-400">
          ({start.toLocaleString('en-IN')}-{end.toLocaleString('en-IN')} of {total.toLocaleString('en-IN')})
        </span>
      </div>

      {totalPages > 1 && (
        <nav className="flex items-center gap-1 flex-wrap justify-center" aria-label="Pagination">
          <PageBtn
            label="<"
            title="Previous page"
            disabled={page === 1}
            onClick={() => onPageChange(page - 1)}
          />

          {pageNumbers.map((n, i) =>
            n === '...' ? (
              <span key={`ellipsis-${i}`} className="w-8 text-center text-gray-400 text-sm select-none">
                ...
              </span>
            ) : (
              <button
                key={n}
                onClick={() => onPageChange(n)}
                aria-current={n === page ? 'page' : undefined}
                className={`w-9 h-9 rounded-lg text-sm font-semibold transition-colors ${
                  n === page
                    ? 'bg-maroon-700 text-white shadow-sm'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {n}
              </button>
            )
          )}

          <PageBtn
            label=">"
            title="Next page"
            disabled={page === totalPages}
            onClick={() => onPageChange(page + 1)}
          />
        </nav>
      )}
    </div>
  )
}

function PageBtn({ label, title, disabled, onClick }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className="px-3 h-9 rounded-lg text-base font-semibold transition-colors
                 bg-gray-100 text-gray-700 hover:bg-gray-200
                 disabled:opacity-35 disabled:cursor-not-allowed"
    >
      {label}
    </button>
  )
}
