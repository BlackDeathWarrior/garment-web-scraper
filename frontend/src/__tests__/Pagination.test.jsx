import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import Pagination from '../components/Pagination'

describe('Pagination', () => {
  it('renders page tabs based on total and per-page size', () => {
    render(
      <Pagination
        total={100}
        perPage={25}
        page={1}
        onPerPageChange={() => {}}
        onPageChange={() => {}}
      />
    )

    expect(screen.getByRole('button', { name: '1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '2' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '3' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '4' })).toBeInTheDocument()
  })

  it('goes to the page that is clicked, and to the next one', () => {
    const onPageChange = vi.fn()

    render(<Pagination total={120} perPage={25} page={2} onPageChange={onPageChange} />)

    fireEvent.click(screen.getByRole('button', { name: '4' }))
    expect(onPageChange).toHaveBeenCalledWith(4)
    fireEvent.click(screen.getByTitle('Next page'))
    expect(onPageChange).toHaveBeenCalledWith(3)
  })

  it('returns null when there are no products', () => {
    const { container } = render(
      <Pagination
        total={0}
        perPage={25}
        page={1}
        onPerPageChange={() => {}}
        onPageChange={() => {}}
      />
    )
    expect(container.firstChild).toBeNull()
  })
})
