import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'

const h = vi.hoisted(() => ({
  setTheme: vi.fn(),
  refreshUser: vi.fn(),
    refreshPublicSettings: vi.fn(),
    householdTimeZone: null,
  put: vi.fn(),
  state: { theme: 'dark' as 'dark' | 'light', authed: true, authMode: 'local' as string },
}))

vi.mock('../../contexts/ThemeContext', () => ({
  useTheme: () => ({ theme: h.state.theme, setTheme: h.setTheme }),
}))
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    isAuthenticated: h.state.authed,
    authMode: h.state.authMode,
    refreshUser: h.refreshUser,
  }),
}))
vi.mock('../../services/api', () => ({ default: { put: h.put } }))

import { useThemePreference } from '../useThemePreference'

beforeEach(() => {
  vi.clearAllMocks()
  h.state = { theme: 'dark', authed: true, authMode: 'local' }
  h.put.mockResolvedValue({})
})

describe('useThemePreference', () => {
  it('applies locally and persists to the account when authenticated', async () => {
    const { result } = renderHook(() => useThemePreference())
    act(() => result.current.setTheme('light'))
    expect(h.setTheme.mock.calls).toStrictEqual([['light']])
    await waitFor(() => expect(h.put).toHaveBeenCalled())
    expect(h.put.mock.calls).toStrictEqual([['/auth/me', { theme: 'light' }]])
    await waitFor(() => expect(h.refreshUser).toHaveBeenCalledTimes(1))
  })

  it('toggle flips the current theme and persists it', async () => {
    h.state.theme = 'dark'
    const { result } = renderHook(() => useThemePreference())
    act(() => result.current.toggleTheme())
    expect(h.setTheme.mock.calls).toStrictEqual([['light']])
    await waitFor(() => expect(h.put.mock.calls).toStrictEqual([['/auth/me', { theme: 'light' }]]))
  })

  it('does NOT persist when unauthenticated (local-only path)', () => {
    h.state.authed = false
    const { result } = renderHook(() => useThemePreference())
    act(() => result.current.setTheme('light'))
    expect(h.setTheme.mock.calls).toStrictEqual([['light']])
    expect(h.put).not.toHaveBeenCalled()
    expect(h.refreshUser).not.toHaveBeenCalled()
  })

  it('does NOT persist when auth is disabled (authMode none)', () => {
    h.state.authMode = 'none'
    const { result } = renderHook(() => useThemePreference())
    act(() => result.current.setTheme('dark'))
    expect(h.setTheme).toHaveBeenCalledWith('dark')
    expect(h.put).not.toHaveBeenCalled()
  })

  it('keeps the local apply when the account save fails', async () => {
    h.put.mockRejectedValue(new Error('boom'))
    const { result } = renderHook(() => useThemePreference())
    act(() => result.current.setTheme('light'))
    expect(h.setTheme.mock.calls).toStrictEqual([['light']])
    await waitFor(() => expect(h.put).toHaveBeenCalled())
    // Best-effort: the failure is swallowed, so refreshUser is never reached.
    expect(h.refreshUser).not.toHaveBeenCalled()
  })
})
