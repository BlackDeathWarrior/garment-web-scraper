import { fireEvent, render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
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

  it('does not say where the listing was collected from: the shop sells it as its own', () => {
    render(<ProductCard product={{ ...base, source: 'amazon' }} />)
    expect(screen.queryByText('Amazon')).not.toBeInTheDocument()
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

  it('opens the product when clicked, and links nowhere else', () => {
    const onClick = vi.fn()
    render(<ProductCard product={base} onClick={onClick} />)
    fireEvent.click(screen.getByRole('article'))
    expect(onClick).toHaveBeenCalledWith(base)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
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

  it('renders the women flair', () => {
    render(<ProductCard product={{ ...base, target_gender: 'Women' }} />)
    expect(screen.getByText('Women', { selector: 'span' })).toBeInTheDocument()
  })

  it('renders the men flair', () => {
    render(<ProductCard product={{ ...base, target_gender: 'Men' }} />)
    expect(screen.getByText('Men', { selector: 'span' })).toBeInTheDocument()
  })

  it('renders both flairs for a unisex product', () => {
    render(<ProductCard product={{ ...base, target_gender: 'Unisex' }} />)
    expect(screen.getByText('Men', { selector: 'span' })).toBeInTheDocument()
    expect(screen.getByText('Women', { selector: 'span' })).toBeInTheDocument()
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
    expect(screen.getByText(/1\.2K\s+ratings/i)).toBeInTheDocument()
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
    expect(screen.getByText(/2\.3K\s+ratings/i)).toBeInTheDocument()
  })

  it('shows a placeholder picture when the image is missing', () => {
    render(<ProductCard product={{ ...base, image_url: null }} />)
    expect(screen.getByRole('img', { name: /Cotton Straight Kurta/i }).getAttribute('src')).toMatch(
      /^data:image\/svg\+xml/
    )
  })

  it('resets image fallback state when a new product image arrives', () => {
    const { rerender } = render(
      <ProductCard product={{ ...base, product_url: 'https://www.flipkart.com/product/old' }} />
    )

    fireEvent.error(screen.getByRole('img', { name: /Cotton Straight Kurta/i }))
    expect(screen.getByText(/Image Load Failed/i)).toBeInTheDocument()

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

    expect(screen.queryByText(/Image Load Failed/i)).not.toBeInTheDocument()
  })
})
