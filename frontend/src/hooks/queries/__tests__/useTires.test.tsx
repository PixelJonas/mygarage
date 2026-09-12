/**
 * Tire mutations invalidate the odometer caches.
 *
 * Every tire operation publishes, moves or deletes vehicle odometer records,
 * and until this file none of them invalidated `['odometerRecords', vin]`, so
 * the Odometer tab and the nearest-reading suggestion could show a value the
 * server no longer held for the 30-second stale time. Component tests mock
 * the hooks away, so this is the only place the invalidation is observable.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import api from '@/services/api'
import { useDeleteTire, useMountTire, useUpdateMountPeriod } from '../useTires'

const VIN = '1HGCM82633A004352'
const NEAREST_KEY = ['odometerRecords', VIN, 'nearest', '2026-04-10']
const LIST_KEY = ['odometerRecords', VIN]

function harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  queryClient.setQueryData(LIST_KEY, { records: [], total: 0 })
  queryClient.setQueryData(NEAREST_KEY, {
    date: '2026-04-01',
    odometer_km: '100000',
    source: 'manual',
    days_away: -9,
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return { queryClient, wrapper }
}

const invalidated = (qc: QueryClient, key: unknown[]) =>
  qc.getQueryState(key)?.isInvalidated === true

describe('tire mutations invalidate the odometer caches', () => {
  beforeEach(() => {
    vi.mocked(api.post).mockResolvedValue({ data: {} })
    vi.mocked(api.put).mockResolvedValue({ data: {} })
    vi.mocked(api.delete).mockResolvedValue({ data: {} })
  })

  it('a mount invalidates the list and the nearest suggestion', async () => {
    const { queryClient, wrapper } = harness()
    const { result } = renderHook(() => useMountTire(VIN), { wrapper })
    await act(async () => {
      await result.current.mutateAsync({ tireId: 1, position: 'FL' })
    })
    expect(invalidated(queryClient, LIST_KEY)).toBe(true)
    expect(invalidated(queryClient, NEAREST_KEY)).toBe(true)
  })

  it('a period edit invalidates them', async () => {
    const { queryClient, wrapper } = harness()
    const { result } = renderHook(() => useUpdateMountPeriod(VIN), { wrapper })
    await act(async () => {
      await result.current.mutateAsync({ tireId: 1, periodId: 2, notes: 'x' })
    })
    expect(vi.mocked(api.put)).toHaveBeenCalledWith('/vehicles/' + VIN + '/tires/1/mount-periods/2', { notes: 'x' })
    expect(invalidated(queryClient, LIST_KEY)).toBe(true)
    expect(invalidated(queryClient, NEAREST_KEY)).toBe(true)
  })

  it('a delete invalidates them', async () => {
    const { queryClient, wrapper } = harness()
    const { result } = renderHook(() => useDeleteTire(VIN), { wrapper })
    await act(async () => {
      await result.current.mutateAsync(1)
    })
    expect(invalidated(queryClient, LIST_KEY)).toBe(true)
    expect(invalidated(queryClient, NEAREST_KEY)).toBe(true)
  })
})
