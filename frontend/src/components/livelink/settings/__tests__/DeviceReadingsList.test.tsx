/**
 * The reading list, driven through the REAL telemetry unit layer: rendering a
 * value beside its unit is unit behaviour, and a stubbed converter would let
 * a Celsius value reach a Fahrenheit account unconverted.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '../../../../__tests__/test-utils'
import type { DeviceReading } from '@/types/livelink'
import { binarySystemFor, presetUnitsFor } from '@/types/units'

const updateParameter = vi.fn()
vi.mock('@/services/livelinkService', () => ({
  livelinkService: {
    updateParameter: (key: string, body: unknown) => updateParameter(key, body),
  },
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
// The compact list's exact-time tooltips read the 12h/24h preference, which
// lives in the auth context.
vi.mock('@/hooks/useTimeFormat', () => ({ useTimeFormat: () => ({ timeFormat: '24h' }) }))

import DeviceReadingsList from '../DeviceReadingsList'

const reading = (overrides: Partial<DeviceReading>): DeviceReading => ({
  param_key: 'PROPANE_T1_LEVEL_PCT',
  display_name: 'Tank 1 level',
  unit: '%',
  value: 71,
  timestamp: '2026-09-22T12:00:00Z',
  show_on_dashboard: true,
  format: 'value',
  ...overrides,
})

beforeEach(() => {
  vi.clearAllMocks()
  updateParameter.mockResolvedValue({})
})

describe('DeviceReadingsList', () => {
  it('converts a Celsius reading for a Fahrenheit account', () => {
    render(
      <DeviceReadingsList
        readings={[reading({ param_key: 'PROPANE_T1_TEMP_C', display_name: 'Tank 1 temperature', unit: 'C', value: 20 })]}
        onChanged={vi.fn()}
      />,
    )

    expect(screen.getByText('Tank 1 temperature')).toBeInTheDocument()
    expect(screen.getByText(/^68/)).toBeInTheDocument()
    expect(screen.getByText('°F')).toBeInTheDocument()
  })

  it('shows a mapped reading that has never reported, with its switch', () => {
    // The ordinary state between applying a preset and the first publish.
    render(
      <DeviceReadingsList
        readings={[reading({ value: null, timestamp: null })]}
        onChanged={vi.fn()}
      />,
    )

    expect(screen.getByText('integrations.readingNone')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Tank 1 level' })).toBeChecked()
  })

  it('switching a reading off writes only show_on_dashboard, then refetches', async () => {
    // archive_only is the chart picker's flag, not this switch's.
    const onChanged = vi.fn()
    render(
      <DeviceReadingsList
        readings={[reading({ param_key: 'PROPANE_T1_QUALITY', display_name: 'Tank 1 reading quality', unit: null, value: 3 })]}
        onChanged={onChanged}
      />,
    )

    fireEvent.click(screen.getByRole('checkbox', { name: 'Tank 1 reading quality' }))

    await waitFor(() =>
      expect(updateParameter).toHaveBeenCalledWith('PROPANE_T1_QUALITY', { show_on_dashboard: false }),
    )
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
  })

  it('puts the switch back and says why when the write fails', async () => {
    updateParameter.mockRejectedValue(new Error('offline'))
    render(<DeviceReadingsList readings={[reading({})]} onChanged={vi.fn()} />)
    const toggle = screen.getByRole('checkbox', { name: 'Tank 1 level' })

    fireEvent.click(toggle)

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    await waitFor(() => expect(toggle).toBeChecked())
  })

  it('follows the server when new readings arrive, not the last click', async () => {
    const { rerender } = render(<DeviceReadingsList readings={[reading({})]} onChanged={vi.fn()} />)
    fireEvent.click(screen.getByRole('checkbox', { name: 'Tank 1 level' }))
    await waitFor(() => expect(updateParameter).toHaveBeenCalled())
    expect(screen.getByRole('checkbox', { name: 'Tank 1 level' })).not.toBeChecked()

    // The refetch says it is shown after all (say another admin switched it back).
    rerender(<DeviceReadingsList readings={[reading({ show_on_dashboard: true })]} onChanged={vi.fn()} />)

    expect(screen.getByRole('checkbox', { name: 'Tank 1 level' })).toBeChecked()
  })
})

describe('DeviceReadingsList compact', () => {
  const tank = (suffix: string, name: string, overrides: Partial<DeviceReading> = {}): DeviceReading =>
    reading({ param_key: `PROPANE_T3_${suffix}`, display_name: `Front tank ${name}`, ...overrides })

  it("drops the sensor's name from each reading, but not from its switch", () => {
    // Two tanks' "Level" switches must not read alike to a screen reader.
    render(
      <DeviceReadingsList compact sensorLabel="Front tank" readings={[tank('LEVEL_PCT', 'level')]} onChanged={vi.fn()} />,
    )

    expect(screen.getByText('Level')).toBeInTheDocument()
    expect(screen.queryByText('Front tank level')).not.toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Front tank level' })).toBeInTheDocument()
  })

  it('shows a name set by hand whole', () => {
    render(
      <DeviceReadingsList
        compact
        sensorLabel="Front tank"
        readings={[reading({ param_key: 'PROPANE_T3_TEMP_C', display_name: 'Bottle temp', unit: 'C', value: 20 })]}
        onChanged={vi.fn()}
      />,
    )

    expect(screen.getByText('Bottle temp')).toBeInTheDocument()
  })

  it('says how old the sensor is once, not on every row', () => {
    render(
      <DeviceReadingsList
        compact
        sensorLabel="Front tank"
        readings={[
          tank('LEVEL_PCT', 'level'),
          tank('SENSOR_BATT_PCT', 'battery', { value: 90, timestamp: '2026-09-22T11:55:00Z' }),
        ]}
        onChanged={vi.fn()}
      />,
    )

    expect(screen.getAllByText('integrations.lastReading')).toHaveLength(1)
    expect(screen.queryByText(/ ago$/)).not.toBeInTheDocument()
  })

  it("marks a value much older than the sensor's newest, and only that one", () => {
    // Level 12:00, depth 10:00: the gateway stopped sending depth.
    render(
      <DeviceReadingsList
        compact
        sensorLabel="Front tank"
        readings={[
          tank('LEVEL_PCT', 'level'),
          tank('DEPTH_MM', 'depth', { unit: 'mm', value: 250, timestamp: '2026-09-22T10:00:00Z' }),
        ]}
        onChanged={vi.fn()}
      />,
    )

    expect(screen.getAllByText('integrations.readingOld')).toHaveLength(1)
    // 250 mm reads 9.8 in for this imperial account (250 / 25.4 = 9.84).
    expect(screen.getByText('integrations.readingOld').parentElement).toHaveTextContent('9.8')
  })

  it('gives each value its exact time on hover', () => {
    render(
      <DeviceReadingsList compact sensorLabel="Front tank" readings={[tank('LEVEL_PCT', 'level')]} onChanged={vi.fn()} />,
    )

    expect(screen.getByText(/^71/).closest('[title]')?.getAttribute('title')).toMatch(/2026/)
  })

  it('shows a reading the way it says: Yes for heard, a grade for quality', () => {
    // The same helper the Live tab's tank card uses, so the two agree.
    render(
      <DeviceReadingsList
        compact
        sensorLabel="Front tank"
        readings={[
          tank('AVAILABLE', 'sensor heard', { unit: null, value: 1, format: 'boolean' }),
          tank('QUALITY', 'reading quality', { unit: null, value: 3, format: 'of_max', max_value: 3 }),
        ]}
        onChanged={vi.fn()}
      />,
    )

    expect(screen.getByText('common:yes')).toBeInTheDocument()
    expect(screen.getByText('common:ofMax')).toBeInTheDocument()
    expect(screen.queryByText('1.0')).not.toBeInTheDocument()
  })

  it('says nothing about age when the sensor has never reported', () => {
    render(
      <DeviceReadingsList
        compact
        sensorLabel="Front tank"
        readings={[tank('LEVEL_PCT', 'level', { value: null, timestamp: null })]}
        onChanged={vi.fn()}
      />,
    )

    expect(screen.queryByText('integrations.lastReading')).not.toBeInTheDocument()
    expect(screen.getByText('integrations.readingNone')).toBeInTheDocument()
  })
})
