/**
 * DeviceTable owns the per-device actions a drawer offers, and tells the
 * drawer when something changed so it can reload and refresh the card.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { LiveLinkDevice } from '@/types/livelink'

const listSources = vi.fn()
const deleteDevice = vi.fn()
vi.mock('@/services/livelinkService', () => ({
  livelinkService: {
    listSources: () => listSources(),
    deleteDevice: (id: string) => deleteDevice(id),
    getDeviceParamKeys: () => Promise.resolve([]),
  },
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }))

import DeviceTable from '../DeviceTable'

const make = (id: string): LiveLinkDevice =>
  ({
    device_id: id,
    kind: 'wican',
    label: id,
    vin: null,
    enabled: true,
    device_status: 'offline',
    ecu_status: 'unknown',
    fw_version: '4.50',
    sta_ip: null,
    has_device_token: false,
  }) as unknown as LiveLinkDevice

beforeEach(() => {
  vi.clearAllMocks()
  listSources.mockResolvedValue([
    { kind: 'wican', capabilities: ['commands', 'odometer', 'sd_backfill', 'telemetry'], syncs_odometer: true },
  ])
  deleteDevice.mockResolvedValue(undefined)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('DeviceTable', () => {
  it('deletes after confirmation, then tells the drawer', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const onChanged = vi.fn()
    render(<DeviceTable devices={[make('d1')]} vehicles={[]} onChanged={onChanged} />)

    fireEvent.click(screen.getByTitle('modal.livelink.deleteDevice'))

    await waitFor(() => expect(deleteDevice).toHaveBeenCalledWith('d1'))
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
  })

  it('does nothing when the confirmation is declined', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const onChanged = vi.fn()
    render(<DeviceTable devices={[make('d1')]} vehicles={[]} onChanged={onChanged} />)

    fireEvent.click(screen.getByTitle('modal.livelink.deleteDevice'))

    expect(deleteDevice).not.toHaveBeenCalled()
    expect(onChanged).not.toHaveBeenCalled()
  })

  it('asks for the source catalogue once, not once per row', async () => {
    render(
      <DeviceTable devices={[make('d1'), make('d2'), make('d3')]} vehicles={[]} onChanged={vi.fn()} />,
    )

    // The rows gain their capability-gated controls once it arrives.
    expect(await screen.findAllByTitle('modal.livelink.deviceSettings')).toHaveLength(3)
    expect(listSources).toHaveBeenCalledTimes(1)
  })
})
