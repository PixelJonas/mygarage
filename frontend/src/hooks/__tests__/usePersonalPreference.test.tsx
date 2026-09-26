/**
 * The shared preference reader: the account's value when signed in, else this
 * browser's, else the default, and never a crash when the browser refuses
 * storage (a private window, site data blocked).
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'

const h = vi.hoisted(() => ({ user: null as Record<string, string> | null }))
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: h.user, isAuthenticated: h.user !== null }),
}))

import { usePersonalPreference } from '../usePersonalPreference'
import { asDashboardSort } from '../../constants/dashboardSort'

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
  h.user = null
})

const read = (): string =>
  renderHook(() => usePersonalPreference('dashboard_sort', 'dashboard_sort', asDashboardSort)).result
    .current

describe('usePersonalPreference', () => {
  it("is the account's value, narrowed, when signed in", () => {
    localStorage.setItem('dashboard_sort', 'year-old')
    h.user = { dashboard_sort: 'maintenance' }
    expect(read()).toBe('maintenance')
    h.user = { dashboard_sort: 'retired-order' }
    expect(read()).toBe('name')
  })

  it("is this browser's value when there is no account", () => {
    localStorage.setItem('dashboard_sort', 'year-old')
    expect(read()).toBe('year-old')
  })

  it('is the default when the browser refuses storage', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('The operation is insecure.', 'SecurityError')
    })
    expect(read()).toBe('name')
  })
})
