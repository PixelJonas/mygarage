import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '../../__tests__/test-utils'

const mockGet = vi.fn()
vi.mock('../../services/api', () => ({
  default: { get: (...args: unknown[]) => mockGet(...args) },
}))
vi.mock('../../services/externalVehicleService', () => ({
  listExternalVehicles: vi.fn().mockResolvedValue({ vehicles: [], total: 0 }),
}))
vi.mock('../../components/VehicleStatisticsCard', () => ({
  default: ({ stats }: { stats: { vin: string } }) => (
    <div data-testid="vehicle-card">{stats.vin}</div>
  ),
}))
vi.mock('../../components/VehicleWizard', () => ({ default: () => null }))
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: null, isAuthenticated: false }),
}))

import Dashboard from '../Dashboard'
import { makeVehicleStatistics } from '../../__tests__/factories'

const OK_PAYLOAD = {
  data: {
    total_vehicles: 1,
    vehicles: [
      makeVehicleStatistics({
        vin: 'RETRY000000000001',
        year: 2020,
        make: 'M',
        model: 'D',
        archived_visible: false,
      }),
    ],
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

const SETTINGS_OFF = {
  data: {
    settings: [
      { key: 'family_friends_enabled', value: 'false' },
    ],
  },
}

describe('Dashboard loading/error/retry states', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows the loading status region before data resolves', () => {
    // A never-resolving promise keeps the component in the loading branch.
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<Dashboard />)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('shows the error state, then recovers when Retry succeeds', async () => {
    mockGet.mockImplementation((url: string) => {
      if (String(url).includes('settings')) {
        return Promise.resolve(SETTINGS_OFF)
      }
      return Promise.reject(new Error('boom'))
    })
    render(<Dashboard />)

    // Error EmptyState (title = loadError key under the i18n mock) + retry button.
    expect(await screen.findByText('dashboard.loadError')).toBeInTheDocument()
    const retry = screen.getByRole('button', { name: 'common:retry' })

    // Retry now succeeds -> the grid renders the (stubbed) card, error clears.
    mockGet.mockImplementation((url: string) => {
      if (String(url).includes('settings')) {
        return Promise.resolve(SETTINGS_OFF)
      }
      return Promise.resolve(OK_PAYLOAD)
    })
    fireEvent.click(retry)

    expect(await screen.findByTestId('vehicle-card')).toBeInTheDocument()
    expect(screen.queryByText('dashboard.loadError')).not.toBeInTheDocument()
  })
})
