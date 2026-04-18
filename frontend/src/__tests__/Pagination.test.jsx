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

  it('calls both handlers when per-page option changes', () => {
    const onPerPageChange = vi.fn()
    const onPageChange = vi.fn()

    render(
      <Pagination
        total={120}
        perPage={25}
        page={2}
        onPerPageChange={onPerPageChange}
        onPageChange={onPageChange}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: '50' }))

    expect(onPerPageChange).toHaveBeenCalledWith(50)
    expect(onPageChange).toHaveBeenCalledWith(1)
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
