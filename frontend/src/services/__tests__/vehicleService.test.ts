import { describe, it, expect, vi, beforeEach } from 'vitest'
import vehicleService from '../vehicleService'
import api from '../api'

vi.mock('../api', () => ({
  default: {
    put: vi.fn(),
    get: vi.fn(),
  },
}))

describe('vehicleService.setMainPhoto', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('calls PUT /vehicles/{vin}/photos/main with filename query param', async () => {
    const mockVehicle = { vin: 'TEST123', make: 'Honda', model: 'Civic' }
    vi.mocked(api.put).mockResolvedValue({ data: mockVehicle })

    await vehicleService.setMainPhoto('TEST123', 'photo1.jpg')

    expect(api.put).toHaveBeenCalledWith(
      '/vehicles/TEST123/photos/main',
      null,
      { params: { filename: 'photo1.jpg' } }
    )
  })

  it('returns the vehicle response', async () => {
    const mockVehicle = { vin: 'TEST123', main_photo: 'photo1.jpg' }
    vi.mocked(api.put).mockResolvedValue({ data: mockVehicle })

    const result = await vehicleService.setMainPhoto('TEST123', 'photo1.jpg')

    expect(result).toEqual(mockVehicle)
  })
})

describe('vehicleService.getDetailStats', () => {
  beforeEach(() => vi.clearAllMocks())

  it('GETs /vehicles/{vin}/detail-stats and returns the stats', async () => {
    const stats = {
      overdue_count: 3, upcoming_count: 2, due_soon_count: 0,
      latest_odometer_km: '160000.00', latest_odometer_date: '2026-07-01',
      last_service_date: '2026-06-15', last_fillup_date: '2026-07-10',
      spent_this_year: '1234.50', year: 2026,
    }
    vi.mocked(api.get).mockResolvedValue({ data: stats })
    const result = await vehicleService.getDetailStats('TEST12345678901234')
    expect(api.get).toHaveBeenCalledWith('/vehicles/TEST12345678901234/detail-stats')
    expect(result).toEqual(stats)
  })
})
