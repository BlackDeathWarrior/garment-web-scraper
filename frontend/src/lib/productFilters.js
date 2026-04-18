export const DEFAULT_FILTERS = {
  sources: [],
  brands: [],
  colors: [],
  genders: [],
  categories: [],
  priceBands: [],
  ratingBands: [],
  discountBands: [],
  stockStates: [],
  flags: [],
  sort: 'default',
}

export const VALID_SORT_VALUES = new Set([
  'default',
  'price_asc',
  'price_desc',
  'rating_desc',
  'discount_desc',
])

export const PRICE_BANDS = [
  { value: 'under_500', label: 'Under ₹500', match: (price) => price != null && price < 500 },
  { value: '500_1000', label: '₹500 - ₹999', match: (price) => price != null && price >= 500 && price < 1000 },
  { value: '1000_2000', label: '₹1,000 - ₹1,999', match: (price) => price != null && price >= 1000 && price < 2000 },
  { value: '2000_plus', label: '₹2,000 & Above', match: (price) => price != null && price >= 2000 },
]

export const RATING_BANDS = [
  { value: '4_plus', label: '4★ & Up', match: (rating) => rating != null && rating >= 4 },
  { value: '3_plus', label: '3★ & Up', match: (rating) => rating != null && rating >= 3 },
  { value: 'rated_only', label: 'Rated Items', match: (rating) => rating != null },
]

export const DISCOUNT_BANDS = [
  { value: '20_plus', label: '20% & Above', match: (discount) => discount != null && discount >= 20 },
  { value: '40_plus', label: '40% & Above', match: (discount) => discount != null && discount >= 40 },
  { value: '60_plus', label: '60% & Above', match: (discount) => discount != null && discount >= 60 },
]

export const STOCK_STATES = [
  { value: 'in_stock', label: 'In Stock', match: (product) => product.in_stock !== false },
  { value: 'low_stock', label: 'Low Stock', match: (product) => product.in_stock !== false && product.stock_count != null && product.stock_count <= 5 },
  { value: 'sold_out', label: 'Sold Out', match: (product) => product.in_stock === false },
]

export const QUALITY_FLAGS = [
  { value: 'has_ratings', label: 'Has Ratings', match: (product) => normalizeNumber(product.rating) != null },
  { value: 'has_rating_count', label: 'Has Rating Count', match: (product) => normalizeNumber(product.rating_count) != null },
  { value: 'has_image', label: 'Has Image', match: (product) => Boolean(String(product.image_url ?? '').trim()) },
  { value: 'with_discount', label: 'Has Discount', match: (product) => normalizeNumber(product.discount_percent) != null },
]

function toList(value) {
  return Array.isArray(value)
    ? value.filter((item) => typeof item === 'string' && item.trim() !== '')
    : []
}

export function normalizeStoredFilters(raw) {
  const sort = VALID_SORT_VALUES.has(raw?.sort) ? raw.sort : 'default'
  return {
    sources: toList(raw?.sources),
    brands: toList(raw?.brands),
    colors: toList(raw?.colors),
    genders: toList(raw?.genders),
    categories: toList(raw?.categories),
    priceBands: toList(raw?.priceBands),
    ratingBands: toList(raw?.ratingBands),
    discountBands: toList(raw?.discountBands),
    stockStates: toList(raw?.stockStates),
    flags: toList(raw?.flags),
    sort,
  }
}

export function countActiveFilters(filters) {
  return (
    (filters.sources?.length ?? 0) +
    (filters.brands?.length ?? 0) +
    (filters.colors?.length ?? 0) +
    (filters.genders?.length ?? 0) +
    (filters.categories?.length ?? 0) +
    (filters.priceBands?.length ?? 0) +
    (filters.ratingBands?.length ?? 0) +
    (filters.discountBands?.length ?? 0) +
    (filters.stockStates?.length ?? 0) +
    (filters.flags?.length ?? 0)
  )
}

export function normalizeNumber(value) {
  if (value == null || value === '') return null
  const match = String(value).replace(/,/g, '').match(/(\d+(?:\.\d+)?)/)
  if (!match) return null
  const num = Number(match[1])
  return Number.isFinite(num) ? num : null
}

export function balanceProductsByGender(products) {
  const queues = {
    Men: [],
    Women: [],
    Other: [],
  }

  for (const product of products) {
    const gender = product?.target_gender
    if (gender === 'Men' || gender === 'Women') {
      queues[gender].push(product)
    } else {
      queues.Other.push(product)
    }
  }

  const balanced = []
  const positions = {
    Men: 0,
    Women: 0,
  }
  const primaryGender =
    queues.Women.length > queues.Men.length ? 'Women' : 'Men'
  const secondaryGender = primaryGender === 'Women' ? 'Men' : 'Women'

  while (positions.Men < queues.Men.length || positions.Women < queues.Women.length) {
    if (positions[primaryGender] < queues[primaryGender].length) {
      balanced.push(queues[primaryGender][positions[primaryGender]])
      positions[primaryGender] += 1
    }

    if (positions[secondaryGender] < queues[secondaryGender].length) {
      balanced.push(queues[secondaryGender][positions[secondaryGender]])
      positions[secondaryGender] += 1
    }
  }

  return [...balanced, ...queues.Other]
}

function matchesAnyBand(selectedBands, bands, value) {
  if (!selectedBands?.length) return true
  return selectedBands.some((selected) => bands.find((band) => band.value === selected)?.match(value))
}

function matchesAnyProductBand(selectedBands, bands, product) {
  if (!selectedBands?.length) return true
  return selectedBands.some((selected) => bands.find((band) => band.value === selected)?.match(product))
}

function matchesAllFlags(selectedFlags, product) {
  if (!selectedFlags?.length) return true
  return selectedFlags.every((selected) => QUALITY_FLAGS.find((flag) => flag.value === selected)?.match(product))
}

export function filterProducts(products, search, filters) {
  let result = [...products]

  if (search.trim()) {
    const q = search.toLowerCase()
    result = result.filter(
      (p) =>
        p.title?.toLowerCase().includes(q) ||
        p.brand?.toLowerCase().includes(q) ||
        p.color?.toLowerCase().includes(q) ||
        p.category?.toLowerCase().includes(q)
    )
  }

  if (filters.sources?.length) {
    result = result.filter((p) => filters.sources.includes(p.source))
  }

  if (filters.brands?.length) {
    result = result.filter((p) => filters.brands.includes(p.brand))
  }

  if (filters.colors?.length) {
    result = result.filter((p) => filters.colors.includes(p.color))
  }

  if (filters.genders?.length) {
    result = result.filter((p) => filters.genders.includes(p.target_gender))
  }

  if (filters.categories?.length) {
    result = result.filter((p) => filters.categories.includes(p.category))
  }

  if (filters.priceBands?.length) {
    result = result.filter((p) => matchesAnyBand(filters.priceBands, PRICE_BANDS, normalizeNumber(p.price_current)))
  }

  if (filters.ratingBands?.length) {
    result = result.filter((p) => matchesAnyBand(filters.ratingBands, RATING_BANDS, normalizeNumber(p.rating)))
  }

  if (filters.discountBands?.length) {
    result = result.filter((p) => matchesAnyBand(filters.discountBands, DISCOUNT_BANDS, normalizeNumber(p.discount_percent)))
  }

  if (filters.stockStates?.length) {
    result = result.filter((p) => matchesAnyProductBand(filters.stockStates, STOCK_STATES, p))
  }

  if (filters.flags?.length) {
    result = result.filter((p) => matchesAllFlags(filters.flags, p))
  }

  if (!filters.genders?.length && filters.sort === 'default') {
    result = balanceProductsByGender(result)
  }

  switch (filters.sort) {
    case 'price_asc':
      result.sort((a, b) => (normalizeNumber(a.price_current) ?? Infinity) - (normalizeNumber(b.price_current) ?? Infinity))
      break
    case 'price_desc':
      result.sort((a, b) => (normalizeNumber(b.price_current) ?? 0) - (normalizeNumber(a.price_current) ?? 0))
      break
    case 'rating_desc':
      result.sort((a, b) => (normalizeNumber(b.rating) ?? 0) - (normalizeNumber(a.rating) ?? 0))
      break
    case 'discount_desc':
      result.sort((a, b) => (normalizeNumber(b.discount_percent) ?? 0) - (normalizeNumber(a.discount_percent) ?? 0))
      break
    default:
      break
  }

  return result
}
