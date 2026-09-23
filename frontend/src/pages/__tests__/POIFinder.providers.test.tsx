/**
 * Find POI carries its own search provider settings, in a sidecar, for the
 * people allowed to change them. Adding, editing and removing a provider are
 * admin-only on the server, and everyone in the household uses this page.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '../../__tests__/test-utils'

vi.mock('@/services/api', () => ({
  default: { get: vi.fn(() => Promise.resolve({ data: { recommendations: [] } })), post: vi.fn() },
}))
vi.mock('@/components/MapDisplay', () => ({ default: () => null }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
let auth = { isAdmin: true, authMode: 'local' }
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ isAuthenticated: true, user: {}, ...auth }),
}))
vi.mock('@/components/poi/PoiProvidersDrawer', () => ({
  default: ({ open }: { open: boolean }) => (open ? <p>providers drawer</p> : null),
}))

import POIFinder from '../POIFinder'

const BUTTON = { name: 'settings:integrations.searchProviders' }

beforeEach(() => {
  auth = { isAdmin: true, authMode: 'local' }
})

describe('POIFinder search providers', () => {
  it('opens the providers sidecar for an admin', () => {
    render(<POIFinder />)

    expect(screen.queryByText('providers drawer')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', BUTTON))

    expect(screen.getByText('providers drawer')).toBeInTheDocument()
  })

  it('offers nothing to someone who is not an admin', () => {
    auth = { isAdmin: false, authMode: 'local' }
    render(<POIFinder />)

    expect(screen.queryByRole('button', BUTTON)).not.toBeInTheDocument()
  })

  it('offers it with sign-in switched off, where there is only one user', () => {
    auth = { isAdmin: false, authMode: 'none' }
    render(<POIFinder />)

    expect(screen.getByRole('button', BUTTON)).toBeInTheDocument()
  })
})
