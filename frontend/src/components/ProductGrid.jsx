import ProductCard from './ProductCard'

function stableProductCardKey(product) {
  const source = String(product?.source ?? '').trim().toLowerCase()
  const productUrl = String(product?.product_url ?? '').trim()
  if (source && productUrl) return `${source}::${productUrl}`
  return product?.id ?? product?.title ?? 'product-card'
}

export default function ProductGrid({ products, loading, error, onProductClick }) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">
        {Array.from({ length: 8 }).map((_, idx) => (
          <div
            key={`skeleton-${idx}`}
            className="rounded-xl border border-gray-200 bg-white overflow-hidden card-shadow animate-pulse"
          >
            <div className="aspect-[3/4] bg-gradient-to-br from-amber-100 to-amber-50" />
            <div className="p-4 space-y-2.5">
              <div className="h-3 w-1/3 bg-gray-200 rounded" />
              <div className="h-4 w-11/12 bg-gray-200 rounded" />
              <div className="h-4 w-3/4 bg-gray-200 rounded" />
              <div className="h-3 w-1/2 bg-gray-200 rounded" />
              <div className="h-9 w-full bg-gray-200 rounded-lg mt-3" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex-1 flex items-start justify-center pt-20">
        <div className="text-center max-w-sm">
          <p className="text-5xl mb-4">!</p>
          <p className="text-gray-700 font-medium">Could not load products</p>
          <p className="text-gray-500 text-sm mt-1">{error}</p>
          <p className="text-gray-500 text-xs mt-3">
            Run{' '}
            <code className="bg-gray-100 px-1.5 py-0.5 rounded text-maroon-700 font-mono">
              ./start_scraper.ps1
            </code>{' '}
            to keep data fresh in the background.
          </p>
        </div>
      </div>
    )
  }

  if (!products.length) {
    return (
      <div className="flex-1 flex items-start justify-center pt-20">
        <div className="text-center">
          <p className="text-5xl mb-4">?</p>
          <p className="text-gray-700 font-medium">No products match your filters</p>
          <p className="text-gray-500 text-sm mt-1">Try adjusting or clearing your filters</p>
        </div>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">
      {products.map((product) => (
        <ProductCard 
          key={stableProductCardKey(product)} 
          product={product} 
          onClick={onProductClick} 
        />
      ))}
    </div>
  )
}
