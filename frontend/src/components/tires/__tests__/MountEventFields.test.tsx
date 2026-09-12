import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const useNearestMock = vi.fn()
vi.mock('../../../hooks/queries/useOdometerRecords', () => ({
  useNearestOdometer: (vin: string, date: string) => useNearestMock(vin, date),
}))

vi.mock('../../../hooks/useUnitPreference', () => ({
  useUnitPreference: () => ({
    system: 'metric',
    showBoth: false,
    gallonStandard: 'us',
    units: {
      consumption: 'l_100km',
      distance: 'km',
      length: 'm',
      mass: 'kg',
      pressure: 'kpa',
      secondary_gallon: 'us',
      speed: 'kmh',
      temperature: 'c',
      torque: 'nm',
      tread: 'mm',
      volume: 'L',
    },
  }),
}))

import MountEventFields from '../MountEventFields'

const VIN = '1HGCM82633A004352'
const READING = { date: '2026-04-01', odometer_km: '100000.00', source: 'manual', days_away: -9 }

function renderField(overrides: Partial<React.ComponentProps<typeof MountEventFields>> = {}) {
  const onDateChange = vi.fn()
  const onOdometerChange = vi.fn()
  render(
    <MountEventFields
      vin={VIN}
      idPrefix="mount"
      dateLabel="tireList.eventDate"
      date="2026-04-10"
      onDateChange={onDateChange}
      odometerLabel="tireList.odometer"
      odometer=""
      onOdometerChange={onOdometerChange}
      {...overrides}
    />
  )
  return { onDateChange, onOdometerChange }
}

describe('MountEventFields', () => {
  beforeEach(() => {
    useNearestMock.mockReturnValue({ data: READING, isSuccess: true })
  })

  it('asks for the reading nearest the date it is given', () => {
    renderField()
    expect(useNearestMock).toHaveBeenCalledWith(VIN, '2026-04-10')
    expect(screen.getByLabelText('tireList.eventDate')).toHaveValue('2026-04-10')
  })

  it('shows the suggestion and fills the odometer only on Use', () => {
    const { onOdometerChange } = renderField()
    expect(screen.getByTestId('mount-suggestion')).toHaveTextContent('tireList.suggestion')
    expect(onOdometerChange).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText('tireList.suggestionUse'))
    expect(onOdometerChange).toHaveBeenCalledTimes(1)
    expect(Number(onOdometerChange.mock.calls[0][0])).toBe(100000)
  })

  it('never writes over a value the user typed when a suggestion arrives', () => {
    const { onOdometerChange } = renderField({ odometer: '123' })
    expect(screen.getByLabelText('tireList.odometer')).toHaveValue(123)
    expect(onOdometerChange).not.toHaveBeenCalled()
  })

  it('says so quietly when the vehicle has no readings', () => {
    useNearestMock.mockReturnValue({ data: null, isSuccess: true })
    renderField()
    expect(screen.getByText('tireList.suggestionNone')).toBeInTheDocument()
    expect(screen.queryByText('tireList.suggestionUse')).toBeNull()
  })

  it('renders nothing about a suggestion while the query is unresolved', () => {
    useNearestMock.mockReturnValue({ data: undefined, isSuccess: false })
    renderField()
    expect(screen.queryByTestId('mount-suggestion')).toBeNull()
    expect(screen.queryByText('tireList.suggestionNone')).toBeNull()
  })
})
