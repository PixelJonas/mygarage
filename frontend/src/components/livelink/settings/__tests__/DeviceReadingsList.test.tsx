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

import DeviceReadingsList from '../DeviceReadingsList'

const reading = (overrides: Partial<DeviceReading>): DeviceReading => ({
  param_key: 'PROPANE_T1_LEVEL_PCT',
  display_name: 'Tank 1 level',
  unit: '%',
  value: 71,
  timestamp: '2026-09-22T12:00:00Z',
  show_on_dashboard: true,
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
