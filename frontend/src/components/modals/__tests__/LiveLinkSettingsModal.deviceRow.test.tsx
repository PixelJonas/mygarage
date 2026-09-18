/**
 * DeviceRow firmware cell (plan 2026-09-18, feature B): the update badge, the
 * "Skip this version" action, and the skipped pill + unskip control that
 * replace the badge while skipped_version matches the latest release.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { fireEvent } from '@testing-library/react'
import type { DeviceFirmwareStatus, LiveLinkDevice } from '@/types/livelink'

import { DeviceRow } from '../LiveLinkSettingsModal'

const device = {
  device_id: 'aabbccddeeff',
  label: 'Truck dongle',
  vin: null,
  enabled: true,
  device_status: 'online',
  ecu_status: 'offline',
  hw_version: 'WiCAN-OBD-PRO',
  fw_version: '4.45',
  sta_ip: null,
  has_device_token: false,
  device_address: null,
  sd_backfill_enabled: false,
  odometer_unit: null,
} as unknown as LiveLinkDevice

const firmware = (overrides: Partial<DeviceFirmwareStatus>): DeviceFirmwareStatus =>
  ({
    device_id: device.device_id,
    current_version: '4.45',
    latest_version: '4.50',
    update_available: true,
    release_url: null,
    firmware_track: 'pro',
    skipped_version: null,
    ...overrides,
  }) as DeviceFirmwareStatus

const onSkipFirmware = vi.fn()
const onUnskipFirmware = vi.fn()

function renderRow(deviceFirmware?: DeviceFirmwareStatus) {
  return render(
    <table>
      <tbody>
        <DeviceRow
          device={device}
          vehicles={[]}
          deviceFirmware={deviceFirmware}
          mqttConnected={false}
          onUpdate={vi.fn()}
          onDelete={vi.fn()}
          onGenerateToken={vi.fn()}
          onRevokeToken={vi.fn()}
          onSendCommand={vi.fn()}
          onSetSdConfig={vi.fn()}
          onSdBackfill={vi.fn()}
          onSkipFirmware={onSkipFirmware}
          onUnskipFirmware={onUnskipFirmware}
        />
      </tbody>
    </table>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('DeviceRow firmware cell', () => {
  it('an available update shows the badge and the skip action passes the version the client saw', () => {
    renderRow(firmware({}))
    expect(screen.getByText('modal.livelink.updateBadge')).toBeInTheDocument()
    fireEvent.click(screen.getByTitle('modal.livelink.skipVersion'))
    expect(onSkipFirmware).toHaveBeenCalledWith('aabbccddeeff', '4.50')
  })

  it('a skipped latest version shows the muted pill + unskip instead of the badge', () => {
    renderRow(firmware({ skipped_version: '4.50' }))
    expect(screen.getByText('modal.livelink.skippedBadge')).toBeInTheDocument()
    expect(screen.queryByText('modal.livelink.updateBadge')).not.toBeInTheDocument()
    expect(screen.queryByTitle('modal.livelink.skipVersion')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTitle('modal.livelink.unskip'))
    expect(onUnskipFirmware).toHaveBeenCalledWith('aabbccddeeff')
  })

  it('a stale skip (an even newer release arrived) shows the badge again', () => {
    renderRow(firmware({ skipped_version: '4.50', latest_version: '4.51' }))
    expect(screen.getByText('modal.livelink.updateBadge')).toBeInTheDocument()
    expect(screen.queryByText('modal.livelink.skippedBadge')).not.toBeInTheDocument()
  })

  it('no update means no badge, no pill and no skip action', () => {
    renderRow(firmware({ update_available: false }))
    expect(screen.queryByText('modal.livelink.updateBadge')).not.toBeInTheDocument()
    expect(screen.queryByText('modal.livelink.skippedBadge')).not.toBeInTheDocument()
    expect(screen.queryByTitle('modal.livelink.skipVersion')).not.toBeInTheDocument()
  })
})
