/**
 * LiveLinkLiveTab honours each reading's show-on-dashboard switch.
 *
 * The switch lives in the integrations settings (one per MQTT reading). Before
 * this, `show_on_dashboard` was written at registration and read by nothing,
 * and the Live tab drew every latest value.
 *
 * Real timers and `findBy*`, as the content tests in LiveLinkLiveTab.test.tsx
 * do; the gauge arithmetic is stubbed because this is about which gauges
 * render, not what they say.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '../../../__tests__/test-utils'
import type { TelemetryLatestValue, VehicleLiveLinkStatus } from '../../../types/livelink'
import { presetUnitsFor } from '../../../types/units'

const getVehicleStatus = vi.fn()
vi.mock('@/services/livelinkService', () => ({
  livelinkService: { getVehicleStatus: (vin: string) => getVehicleStatus(vin) },
}))
vi.mock('@/hooks/useUnitPreference', () => ({
  useUnitPreference: () => ({
    system: 'imperial',
    showBoth: false,
    units: presetUnitsFor('imperial', 'us'),
    gallonStandard: 'us',
  }),
}))
vi.mock('@/hooks/useTimeFormat', () => ({ useTimeFormat: () => ({ timeFormat: '12h' }) }))
vi.mock('@/utils/telemetryUnits', () => ({
  convertTelemetryValue: (v: number) => ({ text: String(v), unit: '', unverified: false }),
  getParamDisplayName: (k: string, dn: string | null) => dn ?? k,
}))
vi.mock('@/utils/parseAPITimestamp', () => ({ formatTime: () => '12:00:00' }))

import LiveLinkLiveTab from '../LiveLinkLiveTab'

const value = (overrides: Partial<TelemetryLatestValue>): TelemetryLatestValue => ({
  param_key: 'X',
  value: 1,
  unit: null,
  display_name: null,
  timestamp: '2026-09-22T00:00:00Z',
  in_warning: false,
  show_on_dashboard: true,
  ...overrides,
})

const status = (values: TelemetryLatestValue[]) =>
  ({
    vin: 'V1',
    device_id: 'rvgw',
    capabilities: ['telemetry'],
    device_status: 'online',
    ecu_status: 'unknown',
    rssi: null,
    current_session_id: null,
    latest_values: values,
  }) satisfies VehicleLiveLinkStatus

beforeEach(() => {
  vi.clearAllMocks()
})

describe('LiveLinkLiveTab dashboard switch', () => {
  it('draws no gauge for a reading hidden from the dashboard', async () => {
    getVehicleStatus.mockResolvedValue(
      status([
        value({ param_key: 'PROPANE_T1_LEVEL_PCT', display_name: 'Tank 1 level' }),
        value({
          param_key: 'PROPANE_T1_QUALITY',
          display_name: 'Tank 1 reading quality',
          show_on_dashboard: false,
        }),
      ]),
    )

    render(<LiveLinkLiveTab vin="V1" />)

    expect(await screen.findByText('Tank 1 level')).toBeInTheDocument()
    expect(screen.queryByText('Tank 1 reading quality')).not.toBeInTheDocument()
  })

  it('says the readings are hidden, not absent, when every one is', async () => {
    // "No telemetry" would send the operator hunting for a broken sensor that
    // is reporting fine.
    getVehicleStatus.mockResolvedValue(
      status([value({ param_key: 'PROPANE_T1_QUALITY', show_on_dashboard: false })]),
    )

    render(<LiveLinkLiveTab vin="V1" />)

    expect(await screen.findByText('livelink.allReadingsHidden')).toBeInTheDocument()
    expect(screen.queryByText('livelink.noTelemetry')).not.toBeInTheDocument()
  })

  it('still says there is no telemetry when there is none', async () => {
    getVehicleStatus.mockResolvedValue(status([]))

    render(<LiveLinkLiveTab vin="V1" />)

    expect(await screen.findByText('livelink.noTelemetry')).toBeInTheDocument()
    expect(screen.queryByText('livelink.allReadingsHidden')).not.toBeInTheDocument()
  })
})
