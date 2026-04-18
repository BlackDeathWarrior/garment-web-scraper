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

export default function Pagination({ total, perPage, page, onPageChange }) {
  if (total === 0 || perPage === 0) return null

  const totalPages = Math.ceil(total / perPage)
  if (totalPages <= 1) return null

  const pageNumbers = buildPageNumbers(page, totalPages)

  return (
    <div className="mt-8 flex flex-col items-center gap-4 select-none">
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
