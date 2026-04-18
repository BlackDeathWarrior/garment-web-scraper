import { fireEvent, render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import ProductCard from '../components/ProductCard'

const base = {
  id: 'test_001',
  title: 'W for Woman Cotton Straight Kurta',
  brand: 'W for Woman',
  source: 'flipkart',
  price_current: 899,
  price_original: 1799,
  discount_percent: 50,
  image_url: 'https://example.com/kurta.jpg',
  rating: 4.2,
  rating_count: 1547,
  color: 'Blue',
  fabric: 'Cotton',
  product_url: 'https://www.flipkart.com/product/1',
  category: 'Kurta',
}

describe('ProductCard', () => {
  it('renders product title', () => {
    render(<ProductCard product={base} />)
    expect(screen.getByText(/Cotton Straight Kurta/i)).toBeInTheDocument()
  })

  it('renders brand name', () => {
    render(<ProductCard product={base} />)
    expect(screen.getByText('W for Woman')).toBeInTheDocument()
  })

  it('renders source badge', () => {
    render(<ProductCard product={base} />)
    expect(screen.getByText('Flipkart', { selector: 'span' })).toBeInTheDocument()
  })

  it('renders amazon source badge', () => {
    render(<ProductCard product={{ ...base, source: 'amazon' }} />)
    expect(screen.getByText('Amazon', { selector: 'span' })).toBeInTheDocument()
  })

  it('renders discount badge', () => {
    render(<ProductCard product={base} />)
    expect(screen.getByText(/50%/)).toBeInTheDocument()
  })

  it('renders current price in INR format', () => {
    render(<ProductCard product={base} />)
    expect(screen.getByText(/\u20B9899/)).toBeInTheDocument()
  })

  it('renders strikethrough original price', () => {
    render(<ProductCard product={base} />)
    expect(screen.getByText(/\u20B91,799/)).toBeInTheDocument()
  })

  it('view deal link points to product URL and opens in new tab', () => {
    render(<ProductCard product={base} />)
    const link = screen.getByRole('link', { name: /View Deal/i })
    expect(link).toHaveAttribute('href', base.product_url)
    expect(link).toHaveAttribute('target', '_blank')
  })

  it('hides original price when absent', () => {
    render(<ProductCard product={{ ...base, price_original: null }} />)
    expect(screen.queryByText(/\u20B91,799/)).not.toBeInTheDocument()
  })

  it('hides discount badge when zero', () => {
    render(<ProductCard product={{ ...base, discount_percent: 0 }} />)
    expect(screen.queryByText(/% OFF/)).not.toBeInTheDocument()
  })

  it('hides discount badge when discount is unrealistic', () => {
    render(<ProductCard product={{ ...base, discount_percent: 4740 }} />)
    expect(screen.queryByText(/4740% OFF/)).not.toBeInTheDocument()
  })

  it('renders Myntra source badge', () => {
    render(<ProductCard product={{ ...base, source: 'myntra' }} />)
    expect(screen.getByText('Myntra', { selector: 'span' })).toBeInTheDocument()
  })

  it('renders inferred women flair', () => {
    render(<ProductCard product={base} />)
    expect(screen.getByText('Women', { selector: 'span' })).toBeInTheDocument()
  })

  it('renders inferred men flair', () => {
    render(
      <ProductCard
        product={{
          ...base,
          title: "Manyavar Men's Embroidered Kurta",
          brand: 'Manyavar',
          category: null,
        }}
      />
    )
    expect(screen.getByText('Men', { selector: 'span' })).toBeInTheDocument()
  })

  it('does not render children flair labels', () => {
    render(
      <ProductCard
        product={{
          ...base,
          title: 'Kids Boys Cotton Kurta Set',
          brand: 'Mini Klub',
          category: null,
          target_gender: null,
        }}
      />
    )
    expect(screen.queryByText('Boys', { selector: 'span' })).not.toBeInTheDocument()
    expect(screen.queryByText('Girls', { selector: 'span' })).not.toBeInTheDocument()
  })

  it('shows no-ratings fallback when rating is missing', () => {
    render(<ProductCard product={{ ...base, rating: null, rating_count: null }} />)
    expect(screen.getByText(/No ratings/i)).toBeInTheDocument()
  })

  it('renders rating when provided as string alias fields', () => {
    render(
      <ProductCard
        product={{
          ...base,
          rating: null,
          rating_count: null,
          rating_value: '4.4',
          ratings_count: '1,245',
        }}
      />
    )
    expect(screen.getByText('4.4')).toBeInTheDocument()
    expect(screen.getByText(/\(1.2K\)/i)).toBeInTheDocument()
  })

  it('parses human-readable rating strings', () => {
    render(
      <ProductCard
        product={{
          ...base,
          rating: '4.1 out of 5',
          rating_count: '2.3k',
        }}
      />
    )
    expect(screen.getByText('4.1')).toBeInTheDocument()
    expect(screen.getByText(/\(2.3K\)/i)).toBeInTheDocument()
  })

  it('shows explicit fallback badge when image is missing', () => {
    render(<ProductCard product={{ ...base, image_url: null }} />)
    expect(screen.getByText(/No image/i)).toBeInTheDocument()
  })

  it('resets image fallback state when a new product image arrives', () => {
    const { rerender } = render(
      <ProductCard product={{ ...base, product_url: 'https://www.flipkart.com/product/old' }} />
    )

    fireEvent.error(screen.getByRole('img', { name: /Cotton Straight Kurta/i }))
    expect(screen.getByText(/No image/i)).toBeInTheDocument()

    rerender(
      <ProductCard
        product={{
          ...base,
          title: 'Updated Cotton Straight Kurta',
          image_url: 'https://example.com/updated-kurta.jpg',
          product_url: 'https://www.flipkart.com/product/new',
        }}
      />
    )

    expect(screen.queryByText(/No image/i)).not.toBeInTheDocument()
  })
})
