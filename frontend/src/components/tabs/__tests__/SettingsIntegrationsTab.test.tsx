/**
 * Structural cover for the Integrations tab.
 *
 * Written BEFORE converting the tab's seven hand-rolled
 * `bg-garage-surface rounded-lg border ... p-6` blocks onto `Card` /
 * `CardHeader`, because the file had no test at all: a mechanical refactor of
 * 771 lines with nothing asserting that every section still renders is how a
 * card quietly disappears behind a mis-paired `</div>`.
 *
 * So this asserts the inventory (every section is present, and the two that
 * carry an About sidecar still offer it), plus the provider table's state
 * column, which is a real accessibility fix rather than a cosmetic one: it
 * rendered a bare lucide Check / X with no accessible name, so a screen reader
 * announced an empty cell for every provider.
 */

import { useEffect } from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { SettingsProvider, useSettings } from '@/contexts/SettingsContext'

vi.mock('@/services/api', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}))

// Same reason as SettingsSystemTab.test.tsx: the global setup mock hands back a
// fresh `t` per call, which re-fires the load effects forever. Pin one.
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
  useAuth: () => ({ isAuthenticated: true, isAdmin: true, authMode: 'local', user: {} }),
}))

vi.mock('@/services/livelinkService', () => ({
  livelinkService: {
    getSettings: vi.fn().mockResolvedValue({ enabled: false }),
    getDevices: vi.fn().mockResolvedValue({ total: 3, online_count: 0, devices: [] }),
    getDeviceFirmwareStatus: vi.fn().mockResolvedValue([]),
  },
}))

// Children that fetch on their own; not under test here.
vi.mock('../../settings/WidgetKeysPanel', () => ({ default: () => <div data-testid="widget-keys" /> }))
vi.mock('../../modals/AddProviderModal', () => ({ default: () => null }))
vi.mock('../../modals/EditProviderModal', () => ({ default: () => null }))
// Renders a close control only while open, so a test can close it the way the
// operator does and observe what closing triggers.
vi.mock('../../modals/LiveLinkSettingsModal', () => ({
  default: ({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) =>
    isOpen ? <button onClick={onClose}>close-livelink-modal</button> : null,
}))
// Fetches on its own and has its own suite. Exposes refreshKey and the
// settings callback so this suite can test the wiring between the two.
vi.mock('../../livelink/LiveLinkIntegrationsCard', () => ({
  default: ({
    refreshKey,
    onOpenSettings,
    onAddSource,
  }: {
    refreshKey?: number
    onOpenSettings: (tab: { id: string }) => void
    onAddSource?: () => void
  }) => (
    <div data-testid="livelink-integrations" data-refresh={refreshKey}>
      <button onClick={() => onOpenSettings({ id: 'wican' })}>open-source-settings</button>
      {onAddSource ? <button onClick={onAddSource}>open-add-source</button> : null}
    </div>
  ),
}))
// The settings drawers have their own suites. The stub exposes which target
// is open and a way to close it, so this suite can test the wiring. Its
// hasDedicatedDrawer mirrors the real one's current answer.
vi.mock('../../livelink/settings/LiveLinkSettingsDrawers', () => ({
  hasDedicatedDrawer: () => false,
  default: ({ target, onClose }: { target: { type: string } | null; onClose: () => void }) =>
    target ? (
      <div data-testid="settings-drawer" data-target={target.type}>
        <button onClick={onClose}>close-settings-drawer</button>
      </div>
    ) : null,
}))
// Fetches presets and vehicles on its own; has its own suite.
vi.mock('../../livelink/AddSourceDrawer', () => ({
  default: ({ open, onCreated }: { open: boolean; onCreated: () => void }) =>
    open ? <button onClick={onCreated}>source-created</button> : null,
}))

import api from '@/services/api'
import SettingsIntegrationsTab from '../SettingsIntegrationsTab'

const mockedApi = vi.mocked(api)

const PROVIDERS = [
  {
    name: 'tomtom',
    display_name: 'TomTom Places API',
    enabled: true,
    is_default: false,
    api_usage: 0,
    api_limit: 2500,
    priority: 1,
  },
  {
    name: 'google',
    display_name: 'Google Places',
    enabled: false,
    is_default: false,
    api_usage: 0,
    api_limit: null,
    priority: 2,
  },
]

function ActiveIntegrationsTab() {
  const { setCurrentTabId } = useSettings()
  useEffect(() => {
    setCurrentTabId('integrations')
  }, [setCurrentTabId])
  return <SettingsIntegrationsTab />
}

function renderTab(): void {
  render(
    <SettingsProvider>
      <ActiveIntegrationsTab />
    </SettingsProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedApi.get.mockImplementation((url: string) => {
    if (url === '/settings/poi-providers') {
      return Promise.resolve({ data: { providers: PROVIDERS } })
    }
    return Promise.resolve({ data: { settings: [] } })
  })
})

describe('SettingsIntegrationsTab', () => {
  it('renders every integration section', async () => {
    renderTab()

    // One assertion per card. If a refactor drops or nests one wrongly, the
    // specific name says which.
    for (const key of [
      'integrations.webhooks',
      'integrations.telegramInbound',
      'integrations.llmSection',
      'integrations.nhtsa',
      'integrations.carComplaints',
      'integrations.livelink',
      'integrations.shopFinder',
    ]) {
      expect(await screen.findByText(key), key).toBeInTheDocument()
    }

    // The API keys panel is a separate component, mounted at the top.
    expect(screen.getByTestId('widget-keys')).toBeInTheDocument()
  })

  it('keeps the About sidecar trigger on the two cards that document themselves', async () => {
    renderTab()

    expect(
      await screen.findByRole('button', { name: 'integrations.aboutCarComplaints' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'integrations.aboutLiveLink' }),
    ).toBeInTheDocument()
  })

  it('names the enabled state of each provider in text, not only as an icon', async () => {
    renderTab()

    await waitFor(() => {
      expect(screen.getByText('TomTom Places API')).toBeInTheDocument()
    })

    // Both rows must carry a readable state. The retired Check / X icons had no
    // accessible name, so this assertion is false against that version.
    expect(screen.getByText('integrations.statusActive')).toBeInTheDocument()
    expect(screen.getByText('integrations.statusInactive')).toBeInTheDocument()
  })

  it('describes LiveLink by its sources, not by one vendor', async () => {
    // A new key rather than a rewrite of livelinkDesc: six locales translate
    // the old WiCAN-specific text, and rewriting its English value would leave
    // every one of them silently stale.
    renderTab()

    expect(await screen.findByText('integrations.livelinkSourcesDesc')).toBeInTheDocument()
    expect(screen.queryByText('integrations.livelinkDesc')).not.toBeInTheDocument()
  })

  it('mounts the integrations strip inside the LiveLink card', async () => {
    renderTab()

    expect(await screen.findByTestId('livelink-integrations')).toBeInTheDocument()
    // The old body's Configure button is gone; the strip's per-source
    // Settings button replaces it.
    expect(screen.queryByText('integrations.configureLiveLink')).not.toBeInTheDocument()
  })

  it('refetches the strip when the LiveLink settings modal closes', async () => {
    // Enabling LiveLink or linking a device in the modal changes a tab's
    // status. Without the bump the strip shows the state from before the edit.
    renderTab()

    const strip = await screen.findByTestId('livelink-integrations')
    const before = Number(strip.dataset.refresh)
    fireEvent.click(screen.getByRole('button', { name: 'open-source-settings' }))
    fireEvent.click(await screen.findByRole('button', { name: 'close-livelink-modal' }))

    await waitFor(() =>
      expect(Number(screen.getByTestId('livelink-integrations').dataset.refresh)).toBe(before + 1),
    )
  })

  it('opens the Add-source drawer from the strip', async () => {
    renderTab()

    fireEvent.click(await screen.findByRole('button', { name: 'open-add-source' }))

    expect(await screen.findByRole('button', { name: 'source-created' })).toBeInTheDocument()
  })

  it('a created source refreshes the strip', async () => {
    // So the new tab appears without a reload.
    renderTab()

    const strip = await screen.findByTestId('livelink-integrations')
    const before = Number(strip.dataset.refresh)

    fireEvent.click(screen.getByRole('button', { name: 'open-add-source' }))
    fireEvent.click(await screen.findByRole('button', { name: 'source-created' }))

    await waitFor(() =>
      expect(Number(screen.getByTestId('livelink-integrations').dataset.refresh)).toBe(before + 1),
    )
  })

  it('opens the global LiveLink settings from the gear', async () => {
    // Retention, alerts and the master switch belong to no single source.
    renderTab()

    fireEvent.click(await screen.findByRole('button', { name: 'integrations.livelinkGeneral' }))

    expect(await screen.findByTestId('settings-drawer')).toHaveAttribute('data-target', 'general')
  })

  it('refetches the strip when a settings drawer closes', async () => {
    renderTab()

    const strip = await screen.findByTestId('livelink-integrations')
    const before = Number(strip.dataset.refresh)
    fireEvent.click(screen.getByRole('button', { name: 'integrations.livelinkGeneral' }))
    fireEvent.click(await screen.findByRole('button', { name: 'close-settings-drawer' }))

    await waitFor(() =>
      expect(Number(screen.getByTestId('livelink-integrations').dataset.refresh)).toBe(before + 1),
    )
    expect(screen.queryByTestId('settings-drawer')).not.toBeInTheDocument()
  })
})
