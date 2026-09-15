import { useEffect } from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SettingsProvider, useSettings } from '@/contexts/SettingsContext'

vi.mock('@/services/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
  },
}))

// See SettingsNotificationsTab.test.tsx: the global setup mock returns a fresh
// `t` per call, which re-fires load effects forever. Pin a stable reference.
vi.mock('react-i18next', () => {
  const stableT = (key: string) => key
  return {
    useTranslation: () => ({
      t: stableT,
      i18n: { language: 'en', changeLanguage: () => Promise.resolve() },
    }),
    Trans: ({ children }: { children: React.ReactNode }) => children,
    initReactI18next: { type: '3rdParty', init: () => {} },
  }
})

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    isAuthenticated: true,
    isAdmin: true,
    user: { unit_preference: 'imperial', language: 'en', currency_code: 'USD' },
    refreshUser: vi.fn(),
  }),
}))

// Children with their own data fetching; not under test here.
vi.mock('@/components/ArchivedVehiclesList', () => ({ default: () => null }))
vi.mock('@/components/modals/OIDCModal', () => ({ default: () => null }))
vi.mock('@/components/modals/FamilyManagementModal', () => ({ default: () => null }))

import api from '@/services/api'
import SettingsSystemTab from '../SettingsSystemTab'

const mockedApi = vi.mocked(api)

function ActiveSystemTab() {
  const { setCurrentTabId } = useSettings()
  useEffect(() => {
    setCurrentTabId('system')
  }, [setCurrentTabId])
  return <SettingsSystemTab />
}

function renderTab(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <SettingsProvider>
        <ActiveSystemTab />
      </SettingsProvider>
    </QueryClientProvider>,
  )
}

/**
 * The OIDC admin PUT is a separate call from the settings batch that carries
 * auth_mode, and saving is auto-triggered by any edit on this tab. If the PUT
 * fires unconditionally, an unrelated edit is coupled to it — the exact shape
 * of the bug that stranded auth_mode at "none".
 */
describe('SettingsSystemTab — OIDC config is only written when OIDC changed', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedApi.get.mockImplementation((url: string) => {
      if (url === '/settings') {
        return Promise.resolve({
          data: {
            settings: [
              { key: 'timezone', value: 'UTC' },
              { key: 'auth_mode', value: 'oidc' },
            ],
          },
        })
      }
      if (url === '/auth/oidc/config/admin') {
        return Promise.resolve({
          data: {
            enabled: true,
            provider_name: 'Rauthy',
            issuer_url: 'https://auth.example.com',
            client_id: 'client-id',
            client_secret: '********',
            scopes: 'openid profile email',
            auto_create_users: true,
            admin_group: '',
            username_claim: 'preferred_username',
            email_claim: 'email',
            full_name_claim: 'name',
          },
        })
      }
      if (url === '/auth/users/count') return Promise.resolve({ data: { count: 2 } })
      if (url === '/dashboard') return Promise.resolve({ data: { total_vehicles: 0 } })
      if (url === '/health') return Promise.resolve({ data: { authenticator_detected: false } })
      return Promise.resolve({ data: {} })
    })
    mockedApi.post.mockResolvedValue({ data: { settings: [], total: 0 } })
    mockedApi.put.mockResolvedValue({ data: {} })
  })

  it('does not PUT the OIDC config when only a non-OIDC setting changed', async () => {
    renderTab()
    await waitFor(() => expect(mockedApi.get).toHaveBeenCalledWith('/settings'))

    const timezone = await screen.findByDisplayValue('UTC')
    fireEvent.change(timezone, { target: { value: 'America/Chicago' } })

    await waitFor(
      () =>
        expect(mockedApi.post).toHaveBeenCalledWith(
          '/settings/batch',
          expect.objectContaining({
            settings: expect.objectContaining({ timezone: 'America/Chicago' }),
          }),
        ),
      { timeout: 3000 },
    )

    expect(mockedApi.put).not.toHaveBeenCalledWith(
      '/auth/oidc/config/admin',
      expect.anything(),
    )
  })

  it('PUTs the OIDC config before the settings batch when the auth mode changes', async () => {
    renderTab()
    await waitFor(() => expect(mockedApi.get).toHaveBeenCalledWith('/settings'))

    // Switching modes sets oidc_enabled alongside auth_mode, so OIDC is dirty.
    fireEvent.click(await screen.findByText('auth.local'))

    await waitFor(
      () =>
        expect(mockedApi.put).toHaveBeenCalledWith(
          '/auth/oidc/config/admin',
          expect.objectContaining({ enabled: false }),
        ),
      { timeout: 3000 },
    )
    await waitFor(
      () =>
        expect(mockedApi.post).toHaveBeenCalledWith(
          '/settings/batch',
          expect.objectContaining({
            settings: expect.objectContaining({ auth_mode: 'local' }),
          }),
        ),
      { timeout: 3000 },
    )

    // Config must land before the mode flips, or OIDC is enabled against
    // settings that never saved.
    const putOrder = mockedApi.put.mock.invocationCallOrder[0]
    const postOrder = mockedApi.post.mock.invocationCallOrder[0]
    expect(putOrder).toBeLessThan(postOrder)
  })
})
