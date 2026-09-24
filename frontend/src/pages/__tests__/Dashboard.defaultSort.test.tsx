/**
 * The dashboard opens on this person's default order (Quick Settings), and the
 * sort menu overrides it for the rest of the tab's session (#180).
 *
 * The override only counts over the default it was picked over: a new default,
 * set here or on another device, takes over at once. It is kept per user, so a
 * household member who signs in on the same tab gets their own default.
 *
 * Fixtures are fed in the REVERSE of every order under test except where
 * stated, so "sorted as asked" and "left in input order" cannot agree.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '../../__tests__/test-utils'

const h = vi.hoisted(() => ({
  user: null as { id: number; dashboard_sort: string } | null,
  get: vi.fn(),
}))

vi.mock('../../services/api', () => ({
  default: { get: (...args: unknown[]) => h.get(...args) },
}))
vi.mock('../../services/externalVehicleService', () => ({
  listExternalVehicles: vi.fn().mockResolvedValue({ vehicles: [], total: 0 }),
}))
vi.mock('../../components/VehicleStatisticsCard', () => ({
  default: ({ stats }: { stats: { year: number; make: string } }) => (
    <div data-testid="vehicle-card">{`${stats.year} ${stats.make}`}</div>
  ),
}))
vi.mock('../../components/VehicleWizard', () => ({ default: () => null }))
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: h.user, isAuthenticated: h.user !== null }),
}))

import Dashboard from '../Dashboard'
import { readSortPick, rememberSortPick, sortPickKey } from '../../utils/dashboardSort'

// Name order (year first): 2019 Aston, 2020 Chevy, 2022 BMW.
// Maintenance order (most overdue first): Chevy, BMW, Aston.
const VEHICLES = [
  { vin: 'B', year: 2022, make: 'BMW', overdue: 1 },
  { vin: 'C', year: 2020, make: 'Chevy', overdue: 2 },
  { vin: 'A', year: 2019, make: 'Aston', overdue: 0 },
].map((v) => ({
  vin: v.vin,
  year: v.year,
  make: v.make,
  model: 'X',
  vehicle_type: 'Car',
  overdue_maintenance_count: v.overdue,
  upcoming_maintenance_count: 0,
  archived_at: null,
  archived_visible: false,
  is_shared_with_me: false,
  distance_unit: null,
}))

const NAME = ['2019 Aston', '2020 Chevy', '2022 BMW']
const NEWEST = ['2022 BMW', '2020 Chevy', '2019 Aston']
const MAINTENANCE = ['2020 Chevy', '2022 BMW', '2019 Aston']

const order = (): string[] => screen.getAllByTestId('vehicle-card').map((el) => el.textContent ?? '')

function pick(label: string): void {
  fireEvent.click(screen.getByRole('button', { name: 'dashboard.sortVehicles' }))
  fireEvent.click(screen.getByRole('menuitemradio', { name: label }))
}

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  localStorage.clear()
  h.user = { id: 1, dashboard_sort: 'name' }
  h.get.mockImplementation((url: string) =>
    Promise.resolve(
      String(url).includes('settings')
        ? { data: { settings: [] } }
        : {
            data: {
              total_vehicles: VEHICLES.length,
              vehicles: VEHICLES,
              fleet_health: { overdue_count: 0, upcoming_30d_count: 0, year: 2026, spent_this_year: '0.00', next_due: null },
            },
          },
    ),
  )
})

describe('the dashboard opens on your default order', () => {
  it("opens on the account's default", async () => {
    h.user = { id: 1, dashboard_sort: 'maintenance' }
    render(<Dashboard />)
    await waitFor(() => expect(order()).toEqual(MAINTENANCE))
  })

  it('opens on Name when the account holds an order the app no longer offers', async () => {
    h.user = { id: 1, dashboard_sort: 'by-mileage' }
    render(<Dashboard />)
    await waitFor(() => expect(order()).toEqual(NAME))
  })

  it('reads the default from this browser when there is no account', async () => {
    h.user = null
    localStorage.setItem('dashboard_sort', 'year-new')
    render(<Dashboard />)
    await waitFor(() => expect(order()).toEqual(NEWEST))
  })

  it('follows a default saved in this browser while the dashboard is open', async () => {
    h.user = null
    render(<Dashboard />)
    await waitFor(() => expect(order()).toEqual(NAME))

    // What useSavePersonalPreference does for a browser-only save.
    localStorage.setItem('dashboard_sort', 'maintenance')
    window.dispatchEvent(new StorageEvent('storage', { key: 'dashboard_sort' }))

    await waitFor(() => expect(order()).toEqual(MAINTENANCE))
  })
})

describe('the sort menu overrides the default for this tab', () => {
  it('a menu pick wins over the default, and survives a remount', async () => {
    h.user = { id: 1, dashboard_sort: 'maintenance' }
    const first = render(<Dashboard />)
    await waitFor(() => expect(order()).toEqual(MAINTENANCE))

    pick('vehicles:dashboard.newestFirst')
    await waitFor(() => expect(order()).toEqual(NEWEST))

    first.unmount()
    render(<Dashboard />)
    await waitFor(() => expect(order()).toEqual(NEWEST))
  })

  it('a new default takes over at once, and changing it back does not bring the pick back', async () => {
    const view = render(<Dashboard />)
    await waitFor(() => expect(order()).toEqual(NAME))
    pick('vehicles:dashboard.newestFirst')
    await waitFor(() => expect(order()).toEqual(NEWEST))

    // Saved in Quick Settings while the dashboard is open.
    h.user = { id: 1, dashboard_sort: 'maintenance' }
    view.rerender(<Dashboard />)
    await waitFor(() => expect(order()).toEqual(MAINTENANCE))

    h.user = { id: 1, dashboard_sort: 'name' }
    view.rerender(<Dashboard />)
    await waitFor(() => expect(order()).toEqual(NAME))

    // Nor does coming back to the dashboard later in the same tab.
    view.unmount()
    render(<Dashboard />)
    await waitFor(() => expect(order()).toEqual(NAME))
  })

  it('ignores a pick made over a default that has since changed on another device', async () => {
    rememberSortPick(1, { sort: 'year-new', over: 'name' })
    h.user = { id: 1, dashboard_sort: 'maintenance' }
    render(<Dashboard />)
    await waitFor(() => expect(order()).toEqual(MAINTENANCE))
    // Cleared from the tab too, so the default changing back cannot revive it.
    await waitFor(() => expect(readSortPick(1)).toBeNull())
  })

  it("ignores another user's pick in the same tab", async () => {
    rememberSortPick(2, { sort: 'year-new', over: 'name' })
    render(<Dashboard />)
    await waitFor(() => expect(order()).toEqual(NAME))
  })

  it('opens on the default when the stored pick is not one the menu offers', async () => {
    sessionStorage.setItem(sortPickKey(1), JSON.stringify({ sort: 'by-vibes', over: 'maintenance' }))
    h.user = { id: 1, dashboard_sort: 'maintenance' }
    render(<Dashboard />)
    await waitFor(() => expect(order()).toEqual(MAINTENANCE))
  })

  it('opens on the default when the stored pick is not JSON', async () => {
    sessionStorage.setItem(sortPickKey(1), 'year-new')
    h.user = { id: 1, dashboard_sort: 'maintenance' }
    render(<Dashboard />)
    await waitFor(() => expect(order()).toEqual(MAINTENANCE))
  })
})
