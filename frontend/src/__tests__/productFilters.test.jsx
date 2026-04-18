import { describe, expect, it } from 'vitest'
import {
  DEFAULT_FILTERS,
  balanceProductsByGender,
  filterProducts,
} from '../lib/productFilters'

const sampleProducts = [
  { id: 'm1', title: 'Men 1', target_gender: 'Men', price_current: 1200 },
  { id: 'm2', title: 'Men 2', target_gender: 'Men', price_current: 1400 },
  { id: 'm3', title: 'Men 3', target_gender: 'Men', price_current: 1600 },
  { id: 'm4', title: 'Men 4', target_gender: 'Men', price_current: 1800 },
  { id: 'w1', title: 'Women 1', target_gender: 'Women', price_current: 1100 },
  { id: 'w2', title: 'Women 2', target_gender: 'Women', price_current: 1300 },
]

describe('productFilters gender balancing', () => {
  it('interleaves men and women when one side dominates', () => {
    const result = balanceProductsByGender(sampleProducts)

    expect(result.slice(0, 6).map((product) => product.title)).toEqual([
      'Men 1',
      'Women 1',
      'Men 2',
      'Women 2',
      'Men 3',
      'Men 4',
    ])
  })

  it('balances default browsing when no gender filter is active', () => {
    const result = filterProducts(sampleProducts, '', DEFAULT_FILTERS)

    expect(result.slice(0, 4).map((product) => product.target_gender)).toEqual([
      'Men',
      'Women',
      'Men',
      'Women',
    ])
  })

  it('keeps explicit gender filtering untouched', () => {
    const result = filterProducts(sampleProducts, '', {
      ...DEFAULT_FILTERS,
      genders: ['Women'],
    })

    expect(result.map((product) => product.target_gender)).toEqual(['Women', 'Women'])
  })
})
