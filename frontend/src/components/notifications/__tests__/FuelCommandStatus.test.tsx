import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const api = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/services/api', () => ({ default: api }))

import { FuelCommandStatus } from '../FuelCommandStatus'

describe('FuelCommandStatus', () => {
  it('hides a status it was once shown when the endpoint then refuses', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    api.get.mockResolvedValueOnce({
      data: {
        state: 'listening',
        error_code: null,
        description: null,
        since: '2026-09-23T00:00:00Z',
      },
    })
    render(
      <QueryClientProvider client={client}>
        <FuelCommandStatus />
      </QueryClientProvider>,
    )
    expect(await screen.findByText('telegram.fuel.status.listening')).toBeInTheDocument()

    api.get.mockRejectedValueOnce({ response: { status: 403 } })
    await act(async () => {
      await client.refetchQueries({ queryKey: ['telegram-fuel-status'] })
    })

    await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument())
  })
})
