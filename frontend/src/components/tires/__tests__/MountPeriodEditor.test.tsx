import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'

const useUpdateMock = vi.fn()
vi.mock('../../../hooks/queries/useTires', () => ({
  useUpdateMountPeriod: () => useUpdateMock(),
}))
vi.mock('../../../hooks/queries/useOdometerRecords', () => ({
  useNearestOdometer: () => ({ data: undefined, isSuccess: false }),
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

import MountPeriodEditor from '../MountPeriodEditor'

const VIN = '1HGCM82633A004352'
const TIRE = { id: 9, vin: VIN, position: 'FL', min_tread_mm: '2.0', below_threshold: false, created_at: '2026-01-01T00:00:00', mount_periods: [], readings: [] }
const CLOSED = { id: 4, position: 'FL', mounted_on: '2026-01-10', dismounted_on: '2026-03-10', mounted_odometer_km: '10000.00', dismounted_odometer_km: '12000.00', is_assumed: false, observed_active_on: null, notes: 'first winter' }
const OPEN = { ...CLOSED, id: 5, dismounted_on: null, dismounted_odometer_km: null, notes: null }
const labelFor = (p: string | null | undefined) => `pos-${p}`
const drawer = () => within(screen.getByRole('dialog'))
const input = (id: string) => document.getElementById(id) as HTMLInputElement

describe('MountPeriodEditor', () => {
  const mutate = vi.fn()
  beforeEach(() => {
    mutate.mockReset()
    useUpdateMock.mockReturnValue({ mutate, isPending: false })
  })

  it('seeds every field from a closed period and sends all five', () => {
    render(<MountPeriodEditor vin={VIN} tire={TIRE as never} period={CLOSED as never} open onClose={vi.fn()} labelFor={labelFor} />)
    expect(input('period-mount-date')).toHaveValue('2026-01-10')
    expect(input('period-mount-odometer')).toHaveValue(10000)
    expect(input('period-dismount-date')).toHaveValue('2026-03-10')
    expect(input('period-dismount-odometer')).toHaveValue(12000)
    expect(input('period-notes')).toHaveValue('first winter')
    fireEvent.change(input('period-mount-odometer'), { target: { value: '10500' } })
    fireEvent.click(drawer().getByText('common:save'))
    expect(mutate.mock.calls[0][0]).toEqual({
      tireId: 9,
      periodId: 4,
      mounted_on: '2026-01-10',
      mounted_odometer_km: 10500,
      dismounted_on: '2026-03-10',
      dismounted_odometer_km: 12000,
      notes: 'first winter',
    })
  })

  it('an open period has no dismount fields and sends none', () => {
    render(<MountPeriodEditor vin={VIN} tire={TIRE as never} period={OPEN as never} open onClose={vi.fn()} labelFor={labelFor} />)
    expect(document.getElementById('period-dismount-date')).toBeNull()
    fireEvent.click(drawer().getByText('common:save'))
    const payload = mutate.mock.calls[0][0]
    expect(payload).not.toHaveProperty('dismounted_on')
    expect(payload).not.toHaveProperty('dismounted_odometer_km')
    expect(payload.notes).toBeNull()
  })

  it('clearing a bound sends null, deliberately', () => {
    render(<MountPeriodEditor vin={VIN} tire={TIRE as never} period={CLOSED as never} open onClose={vi.fn()} labelFor={labelFor} />)
    fireEvent.change(input('period-mount-odometer'), { target: { value: '' } })
    fireEvent.click(drawer().getByText('common:save'))
    expect(mutate.mock.calls[0][0].mounted_odometer_km).toBeNull()
  })

  it('refuses to send a closed period without its dismount date', () => {
    render(<MountPeriodEditor vin={VIN} tire={TIRE as never} period={CLOSED as never} open onClose={vi.fn()} labelFor={labelFor} />)
    fireEvent.change(input('period-dismount-date'), { target: { value: '' } })
    fireEvent.click(drawer().getByText('common:save'))
    expect(mutate).not.toHaveBeenCalled()
  })
})
