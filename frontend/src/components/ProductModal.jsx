import { FiX, FiShoppingBag, FiInfo, FiTag, FiTruck, FiStar } from 'react-icons/fi'

const RUPEE = '\u20B9'

export default function ProductModal({ product, onClose }) {
  if (!product) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
      <div className="bg-white w-full max-w-4xl max-h-[90vh] rounded-3xl shadow-2xl overflow-hidden flex flex-col md:flex-row relative">
        <button 
          onClick={onClose}
          className="absolute top-4 right-4 z-10 p-2 bg-white/80 backdrop-blur rounded-full shadow-lg hover:bg-white transition-colors"
        >
          <FiX size={24} className="text-gray-900" />
        </button>

        {/* Left: Image */}
        <div className="w-full md:w-1/2 bg-amber-50 relative overflow-hidden">
          <img 
            src={product.image_url} 
            alt={product.title} 
            className="w-full h-full object-cover"
          />
        </div>

        {/* Right: Content */}
        <div className="w-full md:w-1/2 p-8 overflow-y-auto bg-white flex flex-col">
          <div className="mb-2">
            <span className="text-[10px] uppercase tracking-[0.2em] font-bold text-maroon-700 bg-maroon-50 px-3 py-1 rounded-full">
              {product.brand || 'Premium Collection'}
            </span>
          </div>
          
          <h2 className="text-2xl font-bold text-gray-900 leading-tight mb-4">
            {product.title}
          </h2>

          <div className="flex items-baseline gap-3 mb-6">
            <span className="text-3xl font-bold text-gray-900">{RUPEE}{product.price_current?.toLocaleString('en-IN')}</span>
            {product.price_original > product.price_current && (
              <span className="text-lg text-gray-400 line-through">{RUPEE}{product.price_original?.toLocaleString('en-IN')}</span>
            )}
            {product.discount_percent && (
              <span className="text-emerald-700 font-bold text-sm bg-emerald-50 px-2.5 py-1 rounded-lg">
                {product.discount_percent}% OFF
              </span>
            )}
          </div>

          <div className="space-y-6 flex-1">
            <section>
              <h3 className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-3 flex items-center gap-2">
                <FiInfo size={14} className="text-maroon-700" /> Product Specifications
              </h3>
              <div className="grid grid-cols-2 gap-4">
                <SpecItem label="Fabric" value={product.fabric || 'Premium Blend'} />
                <SpecItem label="Category" value={product.category || 'Ethnic Wear'} />
                <SpecItem label="Color" value={product.color || 'As Shown'} />
                <SpecItem label="Gender" value={product.target_gender || 'Unisex'} />
                <SpecItem label="In Stock" value={product.in_stock ? 'Available' : 'Sold Out'} />
                <SpecItem label="Source" value={product.source} />
              </div>
            </section>

            {product.review_summary && (
              <section>
                <h3 className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-3 flex items-center gap-2">
                  <FiStar size={14} className="text-gold-600" /> Review Summary
                </h3>
                <blockquote className="bg-amber-50/50 border-l-4 border-gold-400 p-4 rounded-r-xl italic text-gray-700 text-sm leading-relaxed">
                  "{product.review_summary}"
                </blockquote>
              </section>
            )}

            {product.delivery_info && (
              <div className="flex items-center gap-2 text-sm text-emerald-700 font-medium bg-emerald-50 p-3 rounded-xl">
                <FiTruck /> {product.delivery_info}
              </div>
            )}
          </div>

          <div className="mt-8 pt-6 border-t border-gray-100">
            <a 
              href={product.product_url} 
              target="_blank" 
              rel="noopener noreferrer"
              className="w-full bg-maroon-700 hover:bg-maroon-800 text-white font-bold py-4 rounded-2xl transition-all shadow-xl shadow-maroon-900/20 flex items-center justify-center gap-2 group"
            >
              <FiShoppingBag className="group-hover:scale-110 transition-transform" />
              Go to {product.source}
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}

function SpecItem({ label, value }) {
  return (
    <div className="bg-gray-50 p-3 rounded-xl border border-gray-100">
      <p className="text-[10px] text-gray-400 uppercase font-bold tracking-wider mb-1">{label}</p>
      <p className="text-sm text-gray-800 font-semibold truncate capitalize">{value}</p>
    </div>
  )
}
