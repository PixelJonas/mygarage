import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '../../__tests__/test-utils'

const mockGet = vi.fn()
vi.mock('../../services/api', () => ({
  default: { get: (...args: unknown[]) => mockGet(...args) },
}))

vi.mock('../../services/externalVehicleService', () => ({
  listExternalVehicles: vi.fn().mockResolvedValue({ vehicles: [], total: 0 }),
}))

vi.mock('../../components/VehicleStatisticsCard', () => ({
  default: ({
    stats,
  }: {
    stats: { year: number | null; make: string | null; model: string | null }
  }) => <div data-testid="vehicle-card">{`${stats.year} ${stats.make} ${stats.model}`}</div>,
}))
vi.mock('../../components/VehicleWizard', () => ({ default: () => null }))
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: null, isAuthenticated: false }),
}))

import Dashboard from '../Dashboard'
import { sortPickKey } from '../../utils/dashboardSort'
import { makeVehicleStatistics } from '../../__tests__/factories'

function vehicle(v: {
  vin: string
  year: number
  make: string
  model: string
  is_shared_with_me?: boolean
}): Record<string, unknown> {
  return makeVehicleStatistics({ archived_visible: false, ...v })
}

function dashboardPayload(vehicles: Record<string, unknown>[]): { data: Record<string, unknown> } {
  return {
    data: {
      total_vehicles: vehicles.length,
      vehicles,
      multi_user_enabled: false,
      total_service_records: 0,
      total_fuel_records: 0,
      total_maintenance_items: 0,
      total_documents: 0,
      total_notes: 0,
      total_photos: 0,
      fleet_health: {
        overdue_count: 0,
        upcoming_30d_count: 0,
        year: 2026,
        spent_this_year: '0.00',
        next_due: null,
      },
    },
  }
}

function settingsPayload(flags: {
  familyFriends?: boolean
}): { data: { settings: { key: string; value: string }[] } } {
  return {
    data: {
      settings: [
        {
          key: 'family_friends_enabled',
          value: flags.familyFriends ? 'true' : 'false',
        },
      ],
    },
  }
}

function mockDashboard(
  vehicles: Record<string, unknown>[],
  flags: { familyFriends?: boolean } = {
    familyFriends: true,
  },
) {
  mockGet.mockImplementation((url: string) => {
    if (String(url).includes('settings')) {
      return Promise.resolve(settingsPayload(flags))
    }
    return Promise.resolve(dashboardPayload(vehicles))
  })
}

const order = (): string[] =>
  screen.getAllByTestId('vehicle-card').map((el) => el.textContent ?? '')

describe('Dashboard sectioned layout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // The sort choice now persists, so it leaks between tests in this file: the
    // first case below picks newest-first and every later case assumes the
    // default. Clear it rather than letting test order decide the assertions.
    sessionStorage.clear()
  })

  it('re-sorts vehicles when a Sort option is chosen', async () => {
    mockDashboard([
      vehicle({ vin: 'A', year: 2019, make: 'Aston', model: 'X' }),
      vehicle({ vin: 'B', year: 2022, make: 'BMW', model: 'X' }),
      vehicle({ vin: 'C', year: 2020, make: 'Chevy', model: 'X' }),
    ])
    render(<Dashboard />)
    await waitFor(() =>
      expect(order()).toEqual(['2019 Aston X', '2020 Chevy X', '2022 BMW X']),
    )

    fireEvent.click(screen.getByRole('button', { name: 'dashboard.sortVehicles' }))
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'vehicles:dashboard.newestFirst' }))

    await waitFor(() =>
      expect(order()).toEqual(['2022 BMW X', '2020 Chevy X', '2019 Aston X']),
    )
  })

  it('remembers the chosen sort order across a remount (#180)', async () => {
    // ★ NEWEST-FIRST, not oldest-first. The default `name` sort keys on
    // `${year} ${make} ${model}`, so it is year-ASCENDING in practice and an
    // oldest-first assertion is satisfied by the default. Only a reversal
    // distinguishes a remembered choice from a forgotten one.
    const three = [
      vehicle({ vin: 'A', year: 2019, make: 'Aston', model: 'X' }),
      vehicle({ vin: 'B', year: 2022, make: 'BMW', model: 'X' }),
      vehicle({ vin: 'C', year: 2020, make: 'Chevy', model: 'X' }),
    ]
    mockDashboard(three)
    const first = render(<Dashboard />)
    await waitFor(() =>
      expect(order()).toEqual(['2019 Aston X', '2020 Chevy X', '2022 BMW X']),
    )

    fireEvent.click(screen.getByRole('button', { name: 'dashboard.sortVehicles' }))
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'vehicles:dashboard.newestFirst' }))
    await waitFor(() =>
      expect(order()).toEqual(['2022 BMW X', '2020 Chevy X', '2019 Aston X']),
    )

    // A remount stands in for the reload in the report: the component is built
    // fresh, so only something outside React can carry the choice over.
    first.unmount()
    mockDashboard(three)
    render(<Dashboard />)

    await waitFor(() =>
      expect(order()).toEqual(['2022 BMW X', '2020 Chevy X', '2019 Aston X']),
    )
  })

  it('falls back to the default sort when the stored value is not a sort option', async () => {
    // Storage is shared with whatever else runs in this origin and survives a
    // deploy, so a stale or hand-edited value must not put the list in a state
    // no menu item matches. Fed in REVERSE of name order, because an unmatched
    // sort option falls through `sortVehicles` and leaves the input order: that
    // is what distinguishes "fell back to name" from "did not sort at all".
    sessionStorage.setItem(sortPickKey(null), JSON.stringify({ sort: 'by-vibes', over: 'name' }))
    mockDashboard([
      vehicle({ vin: 'B', year: 2022, make: 'BMW', model: 'X' }),
      vehicle({ vin: 'A', year: 2019, make: 'Aston', model: 'X' }),
    ])
    render(<Dashboard />)

    await waitFor(() => expect(order()).toEqual(['2019 Aston X', '2022 BMW X']))
  })

  it('splits owned and shared vehicles into sections regardless of Family & Friends', async () => {
    mockDashboard(
      [
        vehicle({ vin: 'OWN', year: 2021, make: 'Owned', model: 'Y' }),
        vehicle({ vin: 'SHR', year: 2021, make: 'Shared', model: 'Y', is_shared_with_me: true }),
      ],
      { familyFriends: false },
    )
    render(<Dashboard />)

    await waitFor(() => expect(order()).toHaveLength(2))
    expect(screen.getByText('dashboard.myVehiclesSection')).toBeInTheDocument()
    expect(screen.getByText('dashboard.sharedWithMeSection')).toBeInTheDocument()
    expect(screen.queryByText('dashboard.familyFriendsSection')).not.toBeInTheDocument()
  })

  it('shows family empty state when the setting is on and nothing is referenced', async () => {
    mockDashboard([vehicle({ vin: 'OWN', year: 2021, make: 'Owned', model: 'Y' })])
    render(<Dashboard />)

    await waitFor(() =>
      expect(screen.getByText('dashboard.familyEmptyTitle')).toBeInTheDocument(),
    )
  })

  it('shows a share-only garage instead of the empty state when the setting is off', async () => {
    // Regression guard: shared vehicles used to be filtered out entirely when
    // the flag was off, so a user with no vehicles of their own landed on the
    // "no vehicles yet" empty state with their shared cars invisible. The
    // setting is global and admin-only, so they could not fix it themselves.
    mockDashboard(
      [vehicle({ vin: 'SHR', year: 2021, make: 'Shared', model: 'Y', is_shared_with_me: true })],
      { familyFriends: false },
    )
    render(<Dashboard />)

    await waitFor(() => expect(order()).toEqual(['2021 Shared Y']))
    expect(screen.getByText('dashboard.sharedWithMeSection')).toBeInTheDocument()
    expect(screen.queryByText('dashboard.noVehiclesYet')).not.toBeInTheDocument()
  })

  it('hides reference vehicles when Family & Friends is off, but keeps shared vehicles', async () => {
    mockDashboard(
      [
        vehicle({ vin: 'OWN', year: 2021, make: 'Owned', model: 'Y' }),
        vehicle({ vin: 'SHR', year: 2021, make: 'Shared', model: 'Y', is_shared_with_me: true }),
      ],
      { familyFriends: false },
    )
    render(<Dashboard />)

    await waitFor(() =>
      expect(order()).toEqual(['2021 Owned Y', '2021 Shared Y']),
    )
    expect(screen.queryByText('dashboard.familyFriendsSection')).not.toBeInTheDocument()
    expect(screen.getByText('2021 Shared Y')).toBeInTheDocument()
  })
})
