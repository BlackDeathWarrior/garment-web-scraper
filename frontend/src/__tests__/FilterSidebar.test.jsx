import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import FilterSidebar from '../components/FilterSidebar'

const mockProducts = [
  { source: 'flipkart', brand: 'W for Woman', color: 'Blue' },
  { source: 'myntra', brand: 'Biba', color: 'Red' },
  { source: 'amazon', brand: 'Libas', color: 'Blue' },
]

const defaultFilters = { sources: [], brands: [], colors: [], genders: [], sort: 'default' }

describe('FilterSidebar', () => {
  it('offers no filter by where a listing was collected from', () => {
    render(
      <FilterSidebar
        filters={defaultFilters}
        onFiltersChange={() => {}}
        products={mockProducts}
        isOpen={true}
        onClose={() => {}}
      />
    )
    expect(screen.queryByText('Flipkart')).not.toBeInTheDocument()
    expect(screen.queryByText('Myntra')).not.toBeInTheDocument()
    expect(screen.queryByText('Amazon')).not.toBeInTheDocument()
  })

  it('renders brand options', () => {
    render(
      <FilterSidebar
        filters={defaultFilters}
        onFiltersChange={() => {}}
        products={mockProducts}
        isOpen={true}
        onClose={() => {}}
      />
    )
    expect(screen.getByText('W for Woman')).toBeInTheDocument()
    expect(screen.getByText('Biba')).toBeInTheDocument()
  })

  it('calls onFiltersChange when sort radio changes', () => {
    const onFiltersChange = vi.fn()
    render(
      <FilterSidebar
        filters={defaultFilters}
        onFiltersChange={onFiltersChange}
        products={mockProducts}
        isOpen={true}
        onClose={() => {}}
      />
    )
    fireEvent.click(screen.getByDisplayValue('price_asc'))
    expect(onFiltersChange).toHaveBeenCalledWith(
      expect.objectContaining({ sort: 'price_asc' })
    )
  })

  it('calls onFiltersChange when a brand checkbox is toggled', () => {
    const onFiltersChange = vi.fn()
    render(
      <FilterSidebar
        filters={defaultFilters}
        onFiltersChange={onFiltersChange}
        products={mockProducts}
        isOpen={true}
        onClose={() => {}}
      />
    )
    fireEvent.click(screen.getAllByRole('checkbox')[0])
    expect(onFiltersChange).toHaveBeenCalled()
  })

  it('shows Clear button when filters are active', () => {
    render(
      <FilterSidebar
        filters={{ ...defaultFilters, brands: ['Biba'] }}
        onFiltersChange={() => {}}
        products={mockProducts}
        isOpen={true}
        onClose={() => {}}
      />
    )
    expect(screen.getByText(/Clear/)).toBeInTheDocument()
  })

  it('calls onClose when backdrop is clicked on mobile', () => {
    const onClose = vi.fn()
    const { container } = render(
      <FilterSidebar
        filters={defaultFilters}
        onFiltersChange={() => {}}
        products={mockProducts}
        isOpen={true}
        onClose={onClose}
      />
    )
    const backdrop = container.querySelector('[aria-hidden="true"]')
    if (backdrop) fireEvent.click(backdrop)
    expect(onClose).toHaveBeenCalled()
  })
})
