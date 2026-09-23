/**
 * Who may change what applies to the whole instance.
 *
 * The server allows it for an admin, and for everyone when sign-in is off
 * (`auth_mode=none` has no user, so `isAdmin` is false for the one person
 * using it). `isAdmin` alone would hide instance settings from exactly that
 * person.
 */
import { describe, it, expect, vi } from 'vitest'
import { renderHook } from '@testing-library/react'

const h = vi.hoisted(() => ({ isAdmin: false, authMode: 'local' }))

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ isAdmin: h.isAdmin, authMode: h.authMode }),
}))

import { useCanManageInstance } from '../useCanManageInstance'

describe('useCanManageInstance', () => {
  it.each([
    [true, 'local', true],
    [true, 'oidc', true],
    [false, 'none', true],
    [false, 'local', false],
    [false, 'oidc', false],
  ])('isAdmin=%s, auth mode %s -> %s', (isAdmin, authMode, expected) => {
    h.isAdmin = isAdmin
    h.authMode = authMode
    expect(renderHook(() => useCanManageInstance()).result.current).toBe(expected)
  })
})
