import { useEffect, useState } from 'react'
import { FiExternalLink, FiInfo, FiShield } from 'react-icons/fi'

const FALLBACK_SRC =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='420' height='560' viewBox='0 0 420 560'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' x2='1' y1='0' y2='1'%3E%3Cstop offset='0%25' stop-color='%23f8efe4'/%3E%3Cstop offset='100%25' stop-color='%23efe3d3'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='420' height='560' fill='url(%23g)'/%3E%3Crect x='24' y='24' width='372' height='512' rx='20' fill='none' stroke='%23cfb18d' stroke-width='3' stroke-dasharray='10 8'/%3E%3Ctext x='50%25' y='44%25' dominant-baseline='middle' text-anchor='middle' font-size='54' fill='%23a07a4b'%3ENo%20Image%3C/text%3E%3Ctext x='50%25' y='55%25' dominant-baseline='middle' text-anchor='middle' font-size='22' fill='%23917857'%3EImage%20Unavailable%3C/text%3E%3C/svg%3E"

const STAR_GLYPHS = '\u2605'.repeat(5)
const RUPEE = '\u20B9'

const SOURCE_STYLE = {
  flipkart: { bg: 'bg-blue-600', label: 'Flipkart' },
  myntra:   { bg: 'bg-pink-600', label: 'Myntra' },
  amazon:   { bg: 'bg-amber-600', label: 'Amazon' },
}

function genderBadgeClass(label) {
  if (label === 'Men')   return 'bg-slate-700 text-white'
  if (label === 'Women') return 'bg-rose-600 text-white'
  return null
}

function parseRatingValue(value) {
  if (value == null || value === '') return null
  const match = String(value).replace(',', '').match(/(\d+(?:\.\d+)?)/)
  if (!match) return null
  const num = Number(match[1])
  if (!Number.isFinite(num) || num <= 0 || num > 5) return null
  return num
}

function parseRatingCount(value) {
  if (value == null || value === '') return null
  const cleaned = String(value).replace(',', '').trim().toLowerCase()
  const match = cleaned.match(/(\d+(?:\.\d+)?)\s*([km]?)/)
  if (!match) return null
  let num = Number(match[1])
  if (match[2] === 'k') num *= 1000
  if (match[2] === 'm') num *= 1000000
  if (!Number.isFinite(num) || num <= 0) return null
  return Math.round(num)
}

function parseDiscountPercent(value) {
  const num = Number(value)
  if (!Number.isFinite(num)) return null
  const pct = Math.round(num)
  if (pct < 1 || pct > 95) return null
  return pct
}

function normalizeImageUrl(value) {
  if (!value) return null
  const raw = String(value).trim()
  if (!raw) return null
  if (raw.startsWith('//')) return `https:${raw}`
  return raw
}

function StarFlair({ rating, count }) {
  if (rating == null) {
    return (
      <div className="flex items-center gap-1.5" aria-label="No ratings available">
        <span className="text-[14px] tracking-[2px] text-gray-300">{STAR_GLYPHS}</span>
        <span className="text-xs font-semibold text-gray-500">No ratings yet</span>
      </div>
    )
  }

  const pct = Math.min((rating / 5) * 100, 100)
  return (
    <div className="flex items-center gap-1.5">
      <div
        className="relative inline-block leading-none select-none"
        title={`${rating.toFixed(1)} out of 5`}
      >
        <span className="text-[14px] tracking-[2px] text-gray-200">{STAR_GLYPHS}</span>
        <span
          className="absolute inset-0 overflow-hidden whitespace-nowrap text-[14px] tracking-[2px] text-amber-500"
          style={{ width: `${pct}%` }}
        >
          {STAR_GLYPHS}
        </span>
      </div>
      <span className="text-sm font-bold text-gray-800">{rating.toFixed(1)}</span>
      {count != null && (
        <span className="text-xs text-gray-500">
          {count >= 1000
            ? `${(count / 1000).toFixed(1)}K`
            : count.toLocaleString('en-IN')}{' '}
          ratings
        </span>
      )}
    </div>
  )
}

function SpecRow({ label, value }) {
  return (
    <p className="text-[12px] text-white/95 drop-shadow-sm">
      <span className="text-[10px] uppercase tracking-wide text-white/75 mr-1 font-semibold">
        {label}
      </span>
      {value}
    </p>
  )
}

export default function ProductCard({ product, onClick }) {
  const [imgError, setImgError] = useState(false)
  const [retryKey, setRetryKey] = useState(0)

  const {
    title,
    brand,
    source,
    price_current,
    price_original,
    discount_percent,
    image_url,
    rating,
    rating_count,
    review_summary,
    color,
    fabric,
    product_url,
    category,
    target_gender,
    in_stock = true,
    stock_count = null,
    delivery_info = null,
  } = product

  const normalizedImageUrl = normalizeImageUrl(image_url)

  useEffect(() => {
    setImgError(false)
  }, [product_url, normalizedImageUrl, retryKey])

  const handleRetry = (e) => {
    e.stopPropagation()
    setRetryKey(k => k + 1)
  }

  const normalizedRating = parseRatingValue(
    rating
    ?? product.rating_value
    ?? product.ratingValue
    ?? product.average_rating
    ?? product.averageRating
  )
  const normalizedRatingCount = parseRatingCount(
    rating_count
    ?? product.ratingCount
    ?? product.ratings_count
    ?? product.total_ratings
    ?? product.totalRatings
    ?? product.reviewCount
  )
  const normalizedDiscount = parseDiscountPercent(discount_percent)

  const isSoldOut = in_stock === false
  const isLowStock = !isSoldOut && stock_count != null && stock_count <= 5
  const showDiscount = !isSoldOut && normalizedDiscount != null
  const hasPrimaryImage = Boolean(normalizedImageUrl)
  const src = SOURCE_STYLE[source] ?? { bg: 'bg-gray-600', label: source }
  
  // Unisex Support: Render multiple badges
  const genders = target_gender === 'Unisex' ? ['Men', 'Women'] : [target_gender].filter(Boolean)

  return (
    <article
      onClick={() => onClick(product)}
      className={`group bg-white rounded-xl overflow-hidden card-shadow cursor-pointer
                  transition-all duration-300 animate-fade-in flex flex-col h-full border border-gray-200/80
                  ${isSoldOut
                    ? 'opacity-70'
                    : 'hover:card-shadow-hover hover:-translate-y-1'}`}
    >
      <div className="relative overflow-hidden bg-amber-50 aspect-[3/4]">
        <img
          key={`${product_url}-${retryKey}`}
          src={!imgError && hasPrimaryImage ? `${normalizedImageUrl}${normalizedImageUrl.includes('?') ? '&' : '?'}retry=${retryKey}` : FALLBACK_SRC}
          alt={title}
          onError={() => setImgError(true)}
          loading="lazy"
          className={`w-full h-full object-cover transition-transform duration-500
                      ${isSoldOut ? 'grayscale' : 'group-hover:scale-105'}`}
        />

        {imgError && (
          <div className="absolute inset-0 bg-white/60 backdrop-blur-sm flex flex-col items-center justify-center p-4 text-center">
             <p className="text-[11px] font-bold text-gray-700 mb-2 uppercase tracking-tighter">Image Load Failed</p>
             <button
               onClick={handleRetry}
               className="bg-maroon-700 text-white text-[10px] font-bold px-3 py-1.5 rounded-lg shadow-lg hover:bg-maroon-800 transition-colors flex items-center gap-1.5"
             >
               <FiInfo size={12} /> Retry Reload
             </button>
          </div>
        )}

        <div className="absolute top-2 left-2 flex flex-col gap-1.5">
          {showDiscount && (
            <span className="bg-emerald-700 text-white text-[11px] font-semibold px-2.5 py-1 rounded-full shadow">
              {normalizedDiscount}% OFF
            </span>
          )}
          {genders.map(g => (
            <span
              key={g}
              className={`${genderBadgeClass(g)} text-[11px] font-semibold px-2.5 py-1 rounded-full uppercase tracking-wide shadow`}
            >
              {g}
            </span>
          ))}
        </div>

        {/* Clean, readable hover hint instead of dark overlay */}
        {!isSoldOut && (
          <div className="absolute inset-x-0 bottom-0 p-4 translate-y-full group-hover:translate-y-0 transition-transform duration-300 bg-white/90 backdrop-blur-sm border-t border-gray-100 flex items-center justify-center">
            <span className="text-[10px] font-bold text-maroon-700 uppercase tracking-widest flex items-center gap-1.5">
              <FiInfo size={12} /> Click for Full Specs
            </span>
          </div>
        )}

        {isSoldOut && (
          <div className="absolute inset-0 bg-black/40 flex items-center justify-center">
            <span className="bg-white text-gray-800 font-bold text-xs px-4 py-1.5
                             rounded-full tracking-widest uppercase shadow">
              Sold Out
            </span>
          </div>
        )}

        <span className={`absolute top-2 right-2 ${src.bg} text-white
                          text-[11px] font-semibold px-2.5 py-1 rounded-full shadow`}>
          {src.label}
        </span>
      </div>

      <div className="p-4 flex flex-col flex-1 gap-2">
        {brand && (
          <p className="text-xs font-semibold text-maroon-800 uppercase tracking-wide truncate">
            {brand}
          </p>
        )}

        <h3 className="text-[15px] font-semibold text-gray-900 line-clamp-2 leading-snug">
          {title}
        </h3>

        {(color || fabric || category) && (
          <p className="text-xs text-gray-600 truncate font-medium">
            {[category, color, fabric].filter(Boolean).join(' | ')}
          </p>
        )}

        <StarFlair rating={normalizedRating} count={normalizedRatingCount} />

        {product.trust_score && (
          <div className="flex items-center gap-1.5 mt-0.5">
            <FiShield size={12} className="text-emerald-600" />
            <span className="text-[11px] font-bold text-emerald-700 tracking-wide">
              {product.trust_score}% AI Trust Score
            </span>
          </div>
        )}

        {isLowStock && (
          <p className="text-xs font-semibold text-amber-700">
            Only {stock_count} left!
          </p>
        )}

        <div className="flex items-baseline gap-2 mt-auto pt-1">
          <span className={`text-lg font-bold ${isSoldOut ? 'text-gray-500' : 'text-gray-900'}`}>
            {RUPEE}{price_current?.toLocaleString('en-IN')}
          </span>
          {!isSoldOut && price_original != null && price_original > price_current && (
            <span className="text-sm text-gray-500 line-through">
              {RUPEE}{price_original.toLocaleString('en-IN')}
            </span>
          )}
        </div>
      </div>
    </article>
  )
}
