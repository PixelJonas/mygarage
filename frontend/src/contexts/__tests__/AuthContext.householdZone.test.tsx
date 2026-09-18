/**
 * AuthContext feeds the household-zone store from `/settings/public` and
 * keeps it current: refreshPublicSettings() on demand, and a rate-limited
 * refetch when the document becomes visible (plan 4.5.1).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { AuthProvider, useAuth } from '../AuthContext'
import { getHouseholdTimeZone, setHouseholdTimeZone } from '../../constants/i18n'

vi.mock('../../services/api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  setCSRFToken: vi.fn(),
  getCSRFToken: vi.fn(),
  clearCSRFToken: vi.fn(),
  setApiAuthMode: vi.fn(),
}))

import api from '../../services/api'

const mockedApi = vi.mocked(api)

function publicPayload(zone: string) {
  return {
    data: {
      settings: [
        { key: 'auth_mode', value: 'none' },
        { key: 'effective_timezone', value: zone },
      ],
    },
  }
}

function Probe() {
  const { refreshPublicSettings, loading } = useAuth()
  return (
    <button disabled={loading} onClick={() => void refreshPublicSettings()}>
      refresh
    </button>
  )
}

let nowSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  vi.clearAllMocks()
  setHouseholdTimeZone(null)
  nowSpy = vi.spyOn(Date, 'now').mockReturnValue(1_000_000)
})

afterEach(() => {
  setHouseholdTimeZone(null)
  nowSpy.mockRestore()
})

const publicCalls = () =>
  mockedApi.get.mock.calls.filter(([url]) => url === '/settings/public').length

describe('AuthContext household zone', () => {
  it('boot reads effective_timezone into the store; refreshPublicSettings picks up a change', async () => {
    mockedApi.get.mockResolvedValue(publicPayload('America/Chicago'))
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    await waitFor(() => expect(getHouseholdTimeZone()).toBe('America/Chicago'))

    mockedApi.get.mockResolvedValue(publicPayload('Europe/Warsaw'))
    screen.getByRole('button').click()
    await waitFor(() => expect(getHouseholdTimeZone()).toBe('Europe/Warsaw'))
  })

  it('visibilitychange refetches once outside the 60s window and not inside it', async () => {
    mockedApi.get.mockResolvedValue(publicPayload('America/Chicago'))
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    await waitFor(() => expect(publicCalls()).toBe(1))

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    })

    // Within 60s of the boot fetch: rate-limited, no refetch.
    nowSpy.mockReturnValue(1_000_000 + 30_000)
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    expect(publicCalls()).toBe(1)

    // Past the window: exactly one refetch...
    nowSpy.mockReturnValue(1_000_000 + 61_000)
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    await waitFor(() => expect(publicCalls()).toBe(2))

    // ...and a second event right after is limited again.
    nowSpy.mockReturnValue(1_000_000 + 62_000)
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    expect(publicCalls()).toBe(2)
  })
})
