import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '../../../__tests__/test-utils'
import { fireEvent } from '@testing-library/react'
import type { IntegrationTab } from '../../../types/livelink'

// The global mock returns the bare key and drops options, so a count is
// invisible to every assertion. This one appends `#count` when a count is
// passed, which is what lets the linked-count test see WHICH count is shown.
// Module-scope t, for the stable identity the global mock's comment explains.
vi.mock('react-i18next', () => {
  const t = (key: string, options?: { count?: number }): string =>
    options?.count === undefined ? key : `${key}#${options.count}`
  const i18n = { language: 'en', changeLanguage: () => Promise.resolve() }
  return { useTranslation: () => ({ t, i18n }) }
})

const getIntegrations = vi.fn()
vi.mock('@/services/livelinkService', () => ({
  livelinkService: { getIntegrations: () => getIntegrations() },
}))

import LiveLinkIntegrationsCard from '../LiveLinkIntegrationsCard'

const tab = (over: Partial<IntegrationTab> = {}): IntegrationTab =>
  ({
    id: 'wican',
    label: 'WiCAN',
    kind: 'wican',
    status: 'ok',
    reason: 'receiving',
    description: null,
    device_count: 2,
    online_count: 2,
    linked_count: 2,
    firmware_updates: 0,
    ...over,
  }) as IntegrationTab

beforeEach(() => {
  vi.clearAllMocks()
  getIntegrations.mockResolvedValue({ tabs: [tab()] })
})

describe('LiveLinkIntegrationsCard', () => {
  it('renders one tab per entry, in the order given', async () => {
    getIntegrations.mockResolvedValue({
      tabs: [
        tab(),
        tab({ id: 'torque', label: 'Torque', kind: 'torque' }),
        tab({ id: 'broker', label: 'Mosquitto', kind: null }),
      ],
    })

    render(<LiveLinkIntegrationsCard onOpenSettings={() => {}} />)

    await waitFor(() => expect(screen.getByRole('tab', { name: 'WiCAN' })).toBeInTheDocument())
    const names = screen.getAllByRole('tab').map((t) => t.textContent)
    expect(names).toEqual(['WiCAN', 'Torque', 'Mosquitto'])
  })

  it('maps each status to its dot tone', async () => {
    getIntegrations.mockResolvedValue({
      tabs: [
        tab({ id: 'a', label: 'A', status: 'ok' }),
        tab({ id: 'b', label: 'B', status: 'attention' }),
        tab({ id: 'c', label: 'C', status: 'off' }),
      ],
    })

    const { container } = render(<LiveLinkIntegrationsCard onOpenSettings={() => {}} />)

    await waitFor(() => expect(screen.getByRole('tab', { name: 'A' })).toBeInTheDocument())
    expect(container.querySelector('.bg-success')).toBeInTheDocument()
    expect(container.querySelector('.bg-warning')).toBeInTheDocument()
    expect(container.querySelector('.bg-danger')).toBeInTheDocument()
  })

  it('treats a status it has never heard of as red, not green', async () => {
    // Fail safe, matching derive_broker_status: a state this code does not
    // know must never read as healthy.
    getIntegrations.mockResolvedValue({ tabs: [tab({ status: 'something_new' })] })

    const { container } = render(<LiveLinkIntegrationsCard onOpenSettings={() => {}} />)

    await waitFor(() => expect(screen.getByRole('tab', { name: 'WiCAN' })).toBeInTheDocument())
    expect(container.querySelector('.bg-danger')).toBeInTheDocument()
    expect(container.querySelector('.bg-success')).not.toBeInTheDocument()
  })

  it('states the status in words, because the dot is aria-hidden', async () => {
    getIntegrations.mockResolvedValue({
      tabs: [tab({ status: 'attention', reason: 'not_linked', online_count: 0, linked_count: 0 })],
    })

    render(<LiveLinkIntegrationsCard onOpenSettings={() => {}} />)

    expect(await screen.findByText('integrations.statusNotLinked')).toBeInTheDocument()
  })

  it('distinguishes not-linked from no-data, which share a status and counts', async () => {
    getIntegrations.mockResolvedValue({
      tabs: [tab({ status: 'attention', reason: 'no_data', online_count: 0, linked_count: 2 })],
    })

    render(<LiveLinkIntegrationsCard onOpenSettings={() => {}} />)

    expect(await screen.findByText('integrations.statusNoData')).toBeInTheDocument()
    expect(screen.queryByText('integrations.statusNotLinked')).not.toBeInTheDocument()
  })

  it('counts LINKED devices, not all devices, under a not-linked status', async () => {
    // The old card said "2 devices linked" under "Not linked to a vehicle"
    // because it counted every device. The two lines must agree.
    getIntegrations.mockResolvedValue({
      tabs: [
        tab({
          status: 'attention',
          reason: 'not_linked',
          device_count: 2,
          online_count: 1,
          linked_count: 0,
        }),
      ],
    })

    render(<LiveLinkIntegrationsCard onOpenSettings={() => {}} />)

    expect(await screen.findByText(/integrationsTab\.devicesLinked#0/)).toBeInTheDocument()
    expect(screen.queryByText(/integrationsTab\.devicesLinked#2/)).not.toBeInTheDocument()
    expect(screen.getByText(/integrationsTab\.devicesOnlineSuffix#1/)).toBeInTheDocument()
  })

  it('shows only the status for a tab with no devices, such as the broker', async () => {
    getIntegrations.mockResolvedValue({
      tabs: [
        tab({
          id: 'broker',
          label: 'Mosquitto',
          kind: null,
          device_count: 0,
          online_count: 0,
          linked_count: 0,
        }),
      ],
    })

    render(<LiveLinkIntegrationsCard onOpenSettings={() => {}} />)

    expect(await screen.findByText('integrations.statusReceiving')).toBeInTheDocument()
    expect(screen.queryByText(/devicesLinked/)).not.toBeInTheDocument()
  })

  it('shows the server description for a preset tab and a translated one otherwise', async () => {
    getIntegrations.mockResolvedValue({
      tabs: [
        tab({
          id: 'device:rvgw',
          label: 'Mopeka',
          kind: 'generic_mqtt',
          description: 'Two Mopeka sensors.',
        }),
        tab({ id: 'torque', label: 'Torque', kind: 'torque' }),
      ],
    })

    render(<LiveLinkIntegrationsCard onOpenSettings={() => {}} />)

    expect(await screen.findByText('Two Mopeka sensors.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Torque' }))
    expect(screen.getByText('integrations.sourceTorqueDescription')).toBeInTheDocument()
  })

  it('switching tabs changes the settings target', async () => {
    const onOpenSettings = vi.fn()
    getIntegrations.mockResolvedValue({
      tabs: [tab(), tab({ id: 'torque', label: 'Torque', kind: 'torque' })],
    })

    render(<LiveLinkIntegrationsCard onOpenSettings={onOpenSettings} />)

    await waitFor(() => expect(screen.getByRole('tab', { name: 'Torque' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('tab', { name: 'Torque' }))
    fireEvent.click(screen.getByRole('button', { name: /sourceSettings/ }))

    expect(onOpenSettings).toHaveBeenCalledWith(expect.objectContaining({ id: 'torque' }))
  })

  it('offers Add source even when the fetch returns nothing', async () => {
    // The chicken-and-egg control: the only entry point that must work when
    // zero devices exist hangs off the card, not off any tab.
    getIntegrations.mockResolvedValue({ tabs: [] })
    const onAddSource = vi.fn()

    render(<LiveLinkIntegrationsCard onOpenSettings={() => {}} onAddSource={onAddSource} />)

    const button = await screen.findByRole('button', { name: 'integrations.addSource' })
    fireEvent.click(button)
    expect(onAddSource).toHaveBeenCalled()
  })

  it('renders no Add source button until a handler is wired', async () => {
    // A button with nowhere to go is worse than none.
    render(<LiveLinkIntegrationsCard onOpenSettings={() => {}} />)

    await waitFor(() => expect(screen.getByRole('tab', { name: 'WiCAN' })).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'integrations.addSource' })).not.toBeInTheDocument()
  })

  it('degrades to a retry instead of blanking when the fetch fails (G8)', async () => {
    getIntegrations.mockRejectedValue(new Error('boom'))

    render(<LiveLinkIntegrationsCard onOpenSettings={() => {}} />)

    expect(await screen.findByText('integrations.integrationsLoadError')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'common:retry' })).toBeInTheDocument()
  })

  it('retry refetches and recovers', async () => {
    getIntegrations.mockRejectedValueOnce(new Error('boom'))

    render(<LiveLinkIntegrationsCard onOpenSettings={() => {}} />)

    fireEvent.click(await screen.findByRole('button', { name: 'common:retry' }))

    expect(await screen.findByRole('tab', { name: 'WiCAN' })).toBeInTheDocument()
    expect(screen.queryByText('integrations.integrationsLoadError')).not.toBeInTheDocument()
  })

  it('refetches when refreshKey changes', async () => {
    const { rerender } = render(
      <LiveLinkIntegrationsCard onOpenSettings={() => {}} refreshKey={0} />,
    )
    await waitFor(() => expect(getIntegrations).toHaveBeenCalledTimes(1))

    rerender(<LiveLinkIntegrationsCard onOpenSettings={() => {}} refreshKey={1} />)

    await waitFor(() => expect(getIntegrations).toHaveBeenCalledTimes(2))
  })

  it('keeps the selected tab across a refetch', async () => {
    getIntegrations.mockResolvedValue({
      tabs: [tab(), tab({ id: 'torque', label: 'Torque', kind: 'torque' })],
    })
    const { rerender } = render(
      <LiveLinkIntegrationsCard onOpenSettings={() => {}} refreshKey={0} />,
    )
    fireEvent.click(await screen.findByRole('tab', { name: 'Torque' }))

    rerender(<LiveLinkIntegrationsCard onOpenSettings={() => {}} refreshKey={1} />)

    await waitFor(() => expect(getIntegrations).toHaveBeenCalledTimes(2))
    expect(screen.getByRole('tab', { name: 'Torque' })).toHaveAttribute('aria-selected', 'true')
  })
})
