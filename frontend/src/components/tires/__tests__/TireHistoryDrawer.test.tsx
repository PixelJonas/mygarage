import { describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'

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

import TireHistoryDrawer, { needsOdometer } from '../TireHistoryDrawer'

const VIN = '1HGCM82633A004352'
const labelFor = (p: string | null | undefined) => (p == null ? 'stored' : `pos-${p}`)

const ASSUMED = {
  id: 1,
  position: 'FL',
  mounted_on: null,
  dismounted_on: '2026-01-15',
  mounted_odometer_km: null,
  dismounted_odometer_km: '3000.00',
  is_assumed: true,
  observed_active_on: '2025-09-04',
  notes: null,
}
const OPEN = {
  id: 2,
  position: 'FL',
  mounted_on: '2026-01-15',
  dismounted_on: null,
  mounted_odometer_km: '3000.00',
  dismounted_odometer_km: null,
  is_assumed: false,
  observed_active_on: null,
  notes: 'winter set',
}
const tire = (overrides: Record<string, unknown> = {}) => ({
  id: 9,
  vin: VIN,
  position: 'FL',
  brand: 'Nokian',
  min_tread_mm: '2.0',
  below_threshold: false,
  installed_date: null,
  blocking_period_ids: [1],
  mount_periods: [ASSUMED, OPEN],
  readings: [],
  created_at: '2026-01-01T00:00:00',
  ...overrides,
})

const drawer = () => within(screen.getByRole('dialog'))

describe('TireHistoryDrawer', () => {
  it('lists periods oldest first with the badges each one earns', () => {
    render(<TireHistoryDrawer tire={tire() as never} open onClose={vi.fn()} onEditPeriod={vi.fn()} labelFor={labelFor} />)
    expect(drawer().getByText('tireList.firstInstalledUnknown')).toBeInTheDocument()
    const rows = drawer().getAllByTestId(/^period-/)
    expect(rows.map((r) => r.getAttribute('data-testid'))).toEqual(['period-1', 'period-2'])
    const first = within(rows[0])
    expect(first.getByText('tireList.periodRange')).toBeInTheDocument()
    expect(first.getByText('tireList.periodAssumed')).toBeInTheDocument()
    expect(first.getByText('tireList.periodNeedsOdometer')).toBeInTheDocument()
    const second = within(rows[1])
    expect(second.getByText('tireList.periodSince')).toBeInTheDocument()
    expect(second.queryByText('tireList.periodAssumed')).toBeNull()
    expect(second.queryByText(/tireList\.period(NeedsOdometer|Check)/)).toBeNull()
    expect(second.getByText('winter set')).toBeInTheDocument()
  })

  it('a fully bounded blocking period is a fault, not a gap', () => {
    const faulted = { ...OPEN, id: 3, dismounted_on: '2026-02-01', dismounted_odometer_km: '2500.00' }
    render(<TireHistoryDrawer tire={tire({ mount_periods: [faulted], blocking_period_ids: [3] }) as never} open onClose={vi.fn()} onEditPeriod={vi.fn()} labelFor={labelFor} />)
    expect(drawer().getByText('tireList.periodCheck')).toBeInTheDocument()
    expect(needsOdometer(faulted as never)).toBe(false)
    expect(needsOdometer(ASSUMED as never)).toBe(true)
  })

  it('an open, blocking period with a known mount odometer needs no odometer', () => {
    // Pins the guard's actual job: a currently-mounted tire has no dismount
    // odometer yet by definition (it hasn't come off), and must never be
    // told to supply one just because some other property makes it a
    // blocker. `dismounted_on == null` short-circuits the guard before
    // `dismounted_odometer_km` is ever inspected.
    const openBlocking = { ...OPEN, id: 4 }
    expect(needsOdometer(openBlocking as never)).toBe(false)
  })

  it('a closed period missing its closing odometer needs one', () => {
    // Pins the branch's true outcome directly: a period that closed but
    // never recorded the odometer at that moment genuinely needs one.
    const closedMissingDismountOdometer = {
      ...OPEN,
      id: 5,
      dismounted_on: '2026-02-01',
      dismounted_odometer_km: null,
    }
    expect(needsOdometer(closedMissingDismountOdometer as never)).toBe(true)
  })

  it('names the first installation when it is known', () => {
    render(<TireHistoryDrawer tire={tire({ installed_date: '2024-11-02', mount_periods: [{ ...OPEN, mounted_on: '2024-11-02' }] }) as never} open onClose={vi.fn()} onEditPeriod={vi.fn()} labelFor={labelFor} />)
    expect(drawer().getByText('tireList.firstInstalled')).toBeInTheDocument()
  })

  it('Edit hands the row\'s period to the caller', () => {
    const onEditPeriod = vi.fn()
    render(<TireHistoryDrawer tire={tire() as never} open onClose={vi.fn()} onEditPeriod={onEditPeriod} labelFor={labelFor} />)
    fireEvent.click(within(drawer().getByTestId('period-2')).getByText('tireList.periodEdit'))
    expect(onEditPeriod).toHaveBeenCalledWith(expect.objectContaining({ id: 2 }))
  })

  it('is empty when there is nothing to show', () => {
    render(<TireHistoryDrawer tire={tire({ mount_periods: [], blocking_period_ids: [] }) as never} open onClose={vi.fn()} onEditPeriod={vi.fn()} labelFor={labelFor} />)
    expect(drawer().getByText('tireList.historyEmpty')).toBeInTheDocument()
  })
})
