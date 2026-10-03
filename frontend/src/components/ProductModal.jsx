import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FiX, FiShoppingCart, FiInfo, FiTruck, FiStar, FiCheck, FiZap } from 'react-icons/fi'
import { addToCart, MAX_QUANTITY, rupees, SIZES, useCartError } from '../lib/cart'

/** A product, with what a shop needs: a size, a quantity, the cart and "buy now". */
export default function ProductModal({ product, onClose }) {
  const [size, setSize] = useState('M')
  const [quantity, setQuantity] = useState(1)
  const [added, setAdded] = useState(false)
  // A signed-in shopper's cart is the shop's: it can refuse (a full cart).
  const refused = useCartError()
  const navigate = useNavigate()

  useEffect(() => {
    setSize('M')
    setQuantity(1)
    setAdded(false)
  }, [product?.id])

  if (!product) return null
  const soldOut = product.in_stock === false

  const add = () => {
    addToCart(product, { size, quantity })
    setAdded(true)
  }
  const buyNow = () => {
    addToCart(product, { size, quantity })
    onClose()
    navigate('/checkout')
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-fade-in"
      role="dialog"
      aria-modal="true"
      aria-label={product.title}
    >
      <div className="bg-white w-full max-w-4xl max-h-[90vh] rounded-3xl shadow-2xl overflow-hidden flex flex-col md:flex-row relative">
        <button
          onClick={onClose}
          aria-label="Close"
          className="absolute top-4 right-4 z-10 p-2 bg-white/80 backdrop-blur rounded-full shadow-lg hover:bg-white transition-colors"
        >
          <FiX size={24} className="text-gray-900" />
        </button>

        <div className="w-full md:w-1/2 bg-amber-50 relative overflow-hidden max-h-64 md:max-h-none">
          <img src={product.image_url} alt={product.title} className="w-full h-full object-cover" />
        </div>

        <div className="w-full md:w-1/2 p-6 sm:p-8 overflow-y-auto bg-white flex flex-col">
          <div className="mb-2">
            <span className="text-[10px] uppercase tracking-[0.2em] font-bold text-maroon-700 bg-maroon-50 px-3 py-1 rounded-full">
              {product.brand || 'Ethnic Threads'}
            </span>
          </div>

          <h2 className="text-2xl font-bold text-gray-900 leading-tight mb-3">{product.title}</h2>

          {product.rating && (
            <p className="flex items-center gap-1.5 text-sm text-gray-600 mb-3">
              <FiStar className="text-gold-600" fill="currentColor" /> {product.rating} out of 5
            </p>
          )}

          <div className="flex items-baseline gap-3 mb-5">
            <span className="text-3xl font-bold text-gray-900">{rupees(product.price_current)}</span>
            {product.price_original > product.price_current && (
              <span className="text-lg text-gray-400 line-through">{rupees(product.price_original)}</span>
            )}
            {product.discount_percent && (
              <span className="text-emerald-700 font-bold text-sm bg-emerald-50 px-2.5 py-1 rounded-lg">
                {product.discount_percent}% OFF
              </span>
            )}
          </div>

          <div className="space-y-5 flex-1">
            <section>
              <h3 className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-3 flex items-center gap-2">
                <FiInfo size={14} className="text-maroon-700" /> Details
              </h3>
              <div className="grid grid-cols-2 gap-3">
                {product.fabric && <SpecItem label="Fabric" value={product.fabric} />}
                <SpecItem label="Category" value={product.category || 'Ethnic Wear'} />
                {product.color && <SpecItem label="Color" value={product.color} />}
                <SpecItem label="For" value={product.target_gender || 'Everyone'} />
              </div>
            </section>

            <section>
              <h3 className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-3">Size</h3>
              <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Size">
                {SIZES.map((option) => (
                  <button
                    key={option}
                    type="button"
                    role="radio"
                    aria-checked={size === option}
                    onClick={() => setSize(option)}
                    className={`px-3.5 py-2 rounded-xl text-xs font-bold border transition-all ${
                      size === option
                        ? 'bg-maroon-700 text-white border-maroon-700'
                        : 'bg-white text-gray-600 border-gray-200 hover:border-maroon-300'
                    }`}
                  >
                    {option}
                  </button>
                ))}
              </div>
            </section>

            <div className="flex items-center gap-2 text-sm text-emerald-700 font-medium bg-emerald-50 p-3 rounded-xl">
              <FiTruck className="shrink-0" /> Free delivery on orders over {rupees(499)}. Returns within 7 days of
              delivery.
            </div>
          </div>

          <div className="mt-6 pt-5 border-t border-gray-100 space-y-3">
            {soldOut ? (
              <p className="text-center font-bold text-gray-500 py-3">Sold out</p>
            ) : (
              <>
                <div className="flex items-center gap-3">
                  <label htmlFor="quantity" className="text-xs font-bold text-gray-400 uppercase tracking-widest">
                    Quantity
                  </label>
                  <select
                    id="quantity"
                    value={quantity}
                    onChange={(e) => setQuantity(Number(e.target.value))}
                    className="px-3 py-2 rounded-xl border border-gray-200 bg-gray-50 text-sm font-semibold"
                  >
                    {Array.from({ length: MAX_QUANTITY }, (_, i) => i + 1).map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    onClick={add}
                    className="bg-white border-2 border-maroon-700 text-maroon-700 hover:bg-maroon-50 font-bold py-3.5 rounded-2xl transition-all flex items-center justify-center gap-2"
                  >
                    {added && !refused ? <FiCheck /> : <FiShoppingCart />}
                    {added && !refused ? 'Added to cart' : 'Add to cart'}
                  </button>
                  <button
                    onClick={buyNow}
                    className="bg-maroon-700 hover:bg-maroon-800 text-white font-bold py-3.5 rounded-2xl transition-all shadow-xl shadow-maroon-900/20 flex items-center justify-center gap-2"
                  >
                    <FiZap /> Buy now
                  </button>
                </div>
                {added && refused && (
                  <p role="alert" className="text-sm text-red-700 text-center">
                    {refused}
                  </p>
                )}
              </>
            )}
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
