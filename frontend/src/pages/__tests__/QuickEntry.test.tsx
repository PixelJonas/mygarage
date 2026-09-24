/**
 * Quick Entry offers what the vehicle page offers, by the same rules
 * (`vehicleLogKinds`). It used to offer every vehicle Fuel Up and Mileage: a
 * fifth wheel got the engine fuel form, never propane, and an odometer it does
 * not have.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

const h = vi.hoisted(() => ({
  vehicles: [] as Array<Record<string, unknown>>,
}))

vi.mock('../../hooks/queries/useQuickEntryVehicles', () => ({
  useQuickEntryVehicles: () => ({
    data: h.vehicles,
    isLoading: false,
    isError: false,
    isFetching: false,
    refetch: vi.fn(),
  }),
}))
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 1 } }) }))

// Each form is its own suite; here only which one opens matters.
vi.mock('../../components/FuelRecordForm', () => ({ default: () => <div>form:fuel</div> }))
vi.mock('../../components/PropaneRecordForm', () => ({ default: () => <div>form:propane</div> }))
vi.mock('../../components/DEFRecordForm', () => ({ default: () => <div>form:def</div> }))
vi.mock('../../components/ServiceVisitForm', () => ({ default: () => <div>form:service</div> }))
vi.mock('../../components/OdometerRecordForm', () => ({ default: () => <div>form:odometer</div> }))
vi.mock('../../components/HoursRecordForm', () => ({ default: () => <div>form:hours</div> }))

import QuickEntry from '../QuickEntry'

const vehicle = (over: Record<string, unknown>) => ({
  vin: 'VIN00000000000001',
  nickname: 'Test',
  year: 2023,
  make: 'Make',
  model: 'Model',
  vehicle_type: 'Car',
  usage_unit: 'distance',
  secondary_usage_enabled: false,
  fuel_type: 'gasoline',
  fuel_type_secondary: null,
  thumbnail_url: null,
  ...over,
})

function renderAt(url = '/quick-entry'): void {
  render(
    <MemoryRouter initialEntries={[url]}>
      <QuickEntry />
    </MemoryRouter>,
  )
}

/** The action buttons, by their title key, in the order shown. */
const offered = (): string[] =>
  screen
    .getAllByRole('button')
    .map((b) => b.textContent?.match(/quickEntry\.(\w+?)(?=quickEntry|$)/)?.[1] ?? '')
    .filter(Boolean)

beforeEach(() => {
  h.vehicles = []
})

describe('QuickEntry actions follow the vehicle', () => {
  it('offers a fifth wheel propane and service, and no fuel or mileage', () => {
    h.vehicles = [vehicle({ vehicle_type: 'FifthWheel', fuel_type: null })]
    renderAt()

    expect(offered()).toEqual(['propane', 'serviceVisit'])
  })

  it('offers a motorhome fuel and propane, service and mileage', () => {
    h.vehicles = [vehicle({ vehicle_type: 'RV' })]
    renderAt()

    expect(offered()).toEqual(['fuelUp', 'propane', 'serviceVisit', 'mileage'])
  })

  it('offers a diesel DEF beside its fuel', () => {
    h.vehicles = [vehicle({ vehicle_type: 'Truck', fuel_type: 'diesel' })]
    renderAt()

    expect(offered()).toEqual(['fuelUp', 'def', 'serviceVisit', 'mileage'])
  })

  it('offers an hours-only machine hours instead of mileage', () => {
    h.vehicles = [vehicle({ vehicle_type: 'Tractor', usage_unit: 'hours' })]
    renderAt()

    expect(offered()).toEqual(['fuelUp', 'serviceVisit', 'engineHours'])
  })

  it('opens the propane form from the propane button', async () => {
    h.vehicles = [vehicle({ vehicle_type: 'FifthWheel', fuel_type: null })]
    renderAt()

    await userEvent.click(screen.getByRole('button', { name: /quickEntry\.propane\b/ }))

    expect(screen.getByText('form:propane')).toBeInTheDocument()
  })
})

describe('QuickEntry deep links follow the vehicle', () => {
  it('reads the "add fuel" shortcut as propane on a fifth wheel', () => {
    h.vehicles = [vehicle({ vehicle_type: 'FifthWheel', fuel_type: null })]
    renderAt('/quick-entry?action=add-fuel')

    expect(screen.getByText('form:propane')).toBeInTheDocument()
    expect(screen.queryByText('form:fuel')).not.toBeInTheDocument()
  })

  it('opens nothing for the odometer shortcut on a trailer', () => {
    h.vehicles = [vehicle({ vehicle_type: 'FifthWheel', fuel_type: null })]
    renderAt('/quick-entry?action=odometer')

    expect(screen.queryByText('form:odometer')).not.toBeInTheDocument()
  })

  it('still opens the fuel form for a car', () => {
    h.vehicles = [vehicle({})]
    renderAt('/quick-entry?action=add-fuel')

    expect(screen.getByText('form:fuel')).toBeInTheDocument()
  })
})
