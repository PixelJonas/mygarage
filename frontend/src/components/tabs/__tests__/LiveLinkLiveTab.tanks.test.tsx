/**
 * A preset sensor's readings go on its tank card, not into the gauge grid.
 * Real unit layer and timestamps; only the service and the preference hooks
 * are stubbed.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '../../../__tests__/test-utils'
import type { TelemetryLatestValue, VehicleLiveLinkStatus } from '../../../types/livelink'
import { binarySystemFor, presetUnitsFor } from '../../../types/units'

const getVehicleStatus = vi.fn()
vi.mock('@/services/livelinkService', () => ({
  livelinkService: { getVehicleStatus: (vin: string) => getVehicleStatus(vin) },
}))
vi.mock('@/hooks/useUnitPreference', () => {
  const units = presetUnitsFor('imperial', 'us')
  return {
    useUnitPreference: () => ({
      system: binarySystemFor(units.volume),
      showBoth: false,
      units,
      gallonStandard: units.secondary_gallon,
    }),
  }
})
vi.mock('@/hooks/useTimeFormat', () => ({ useTimeFormat: () => ({ timeFormat: '12h' }) }))

import LiveLinkLiveTab from '../LiveLinkLiveTab'

const value = (key: string, name: string, over: Partial<TelemetryLatestValue> = {}): TelemetryLatestValue => ({
  param_key: key,
  value: 50,
  unit: null,
  display_name: name,
  timestamp: '2026-09-22T12:00:00Z',
  in_warning: false,
  show_on_dashboard: true,
  ...over,
})

const tank = (n: number) => ({
  device_id: `mopeka-t${n}`,
  label: `Tank ${n}`,
  preset_key: 'mopeka',
  online: true,
  last_seen: '2026-09-22T12:00:00Z',
  fill_key: `PROPANE_T${n}_LEVEL_PCT`,
  readings: [
    { param_key: `PROPANE_T${n}_LEVEL_PCT`, format: 'value' as const, max_value: null },
    { param_key: `PROPANE_T${n}_AVAILABLE`, format: 'boolean' as const, max_value: null },
  ],
})

const status = (
  latest: TelemetryLatestValue[],
  sensors: VehicleLiveLinkStatus['sensors'] = [tank(1), tank(2)],
): VehicleLiveLinkStatus => ({
  vin: 'V1',
  device_id: 'mopeka-t1',
  capabilities: ['telemetry'],
  device_status: 'unknown',
  online: true,
  ecu_status: 'unknown',
  latest_values: latest,
  sensors,
})

const TANK_VALUES = [1, 2].flatMap((n) => [
  value(`PROPANE_T${n}_LEVEL_PCT`, `Tank ${n} level`, { unit: '%' }),
  value(`PROPANE_T${n}_AVAILABLE`, `Tank ${n} sensor heard`, { value: 1 }),
])

beforeEach(() => {
  vi.clearAllMocks()
})

describe('LiveLinkLiveTab tanks', () => {
  it('draws one card per tank, and no gauge tile for their readings', async () => {
    getVehicleStatus.mockResolvedValue(status(TANK_VALUES))
    render(<LiveLinkLiveTab vin="V1" />)

    expect(await screen.findByRole('heading', { name: 'Tank 1' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Tank 2' })).toBeInTheDocument()
    // The tiles' titles are the full display names; the cards use short ones.
    expect(screen.queryByText('Tank 1 sensor heard')).not.toBeInTheDocument()
    expect(screen.getAllByText('Sensor heard')).toHaveLength(2)
  })

  it("keeps the gauge tiles for readings that are no tank's", async () => {
    getVehicleStatus.mockResolvedValue(status([...TANK_VALUES, value('0D-VEHICLESPEED', 'Speed', { unit: 'km/h' })]))
    render(<LiveLinkLiveTab vin="V1" />)

    expect(await screen.findByText('Speed')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Tank 1' })).toBeInTheDocument()
  })

  it('draws no card for a tank whose readings are all hidden, and says everything is hidden', async () => {
    getVehicleStatus.mockResolvedValue(
      status(TANK_VALUES.map((v) => ({ ...v, show_on_dashboard: false }))),
    )
    render(<LiveLinkLiveTab vin="V1" />)

    expect(await screen.findByText('livelink.allReadingsHidden')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Tank 1' })).not.toBeInTheDocument()
  })

  it('leaves the gauge grid alone for a vehicle with no tanks', async () => {
    getVehicleStatus.mockResolvedValue(status([value('0D-VEHICLESPEED', 'Speed', { unit: 'km/h' })], []))
    render(<LiveLinkLiveTab vin="V1" />)

    expect(await screen.findByText('Speed')).toBeInTheDocument()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })
})
