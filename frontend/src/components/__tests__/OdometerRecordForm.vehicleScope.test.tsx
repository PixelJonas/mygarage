/**
 * A mi vehicle on a km account (#172), through the REAL `useUnitPreference`:
 * only `AuthContext` is mocked, so the vehicle scope is what decides the unit.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import { render } from '../../__tests__/test-utils'
import { METRIC_UNITS } from '../../__tests__/factories'
import { VehicleUnitScope } from '../../contexts/VehicleUnitScope'
import type { OdometerRecord } from '../../types/odometer'

const createMutateAsync = vi.fn().mockResolvedValue({})
const updateMutateAsync = vi.fn().mockResolvedValue({})
vi.mock('../../hooks/queries/useOdometerRecords', () => ({
  useCreateOdometerRecord: () => ({ mutateAsync: createMutateAsync }),
  useUpdateOdometerRecord: () => ({ mutateAsync: updateMutateAsync }),
}))
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { unit_preference: 'metric', show_both_units: false, resolved_units: METRIC_UNITS },
    isAuthenticated: true,
    defaultUnitPrefs: null,
  }),
}))

import OdometerRecordForm from '../OdometerRecordForm'

beforeEach(() => vi.clearAllMocks())

const unitLabel = (): string =>
  document.querySelector('label[for="odometer_km"]')?.textContent ?? ''

describe('OdometerRecordForm inside a mi vehicle on a km account', () => {
  it('labels the field in miles and stores a typed mile reading as km', async () => {
    render(
      <VehicleUnitScope distanceUnit="mi">
        <OdometerRecordForm vin="V1" onClose={vi.fn()} onSuccess={vi.fn()} />
      </VehicleUnitScope>,
    )
    expect(unitLabel()).toContain('mi')
    fireEvent.change(document.getElementById('date')!, { target: { value: '2026-03-01' } })
    fireEvent.change(document.getElementById('odometer_km')!, { target: { value: '50000' } })
    fireEvent.click(screen.getByRole('button', { name: 'common:create' }))
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalledTimes(1))
    // 50000 mi x 1.609344 = 80467.2 km.
    expect(createMutateAsync.mock.calls[0][0].odometer_km).toBe(80467.2)
  })

  it('an untouched edit posts the stored km back byte-identical', async () => {
    const record = { id: 7, vin: 'V1', date: '2026-01-01', odometer_km: '80467', notes: '' } as unknown as OdometerRecord
    render(
      <VehicleUnitScope distanceUnit="mi">
        <OdometerRecordForm vin="V1" record={record} onClose={vi.fn()} onSuccess={vi.fn()} />
      </VehicleUnitScope>,
    )
    // 80467 km shows as 50000 mi (49999.88 at zero decimals).
    expect((document.getElementById('odometer_km') as HTMLInputElement).value).toBe('50000')
    fireEvent.change(document.getElementById('date')!, { target: { value: '2026-04-01' } })
    fireEvent.click(screen.getByRole('button', { name: 'common:update' }))
    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalledTimes(1))
    expect(updateMutateAsync.mock.calls[0][0].odometer_km).toBe(80467)
  })

  it('outside any scope the same typing is kilometres (the scope is what changed it)', async () => {
    render(<OdometerRecordForm vin="V1" onClose={vi.fn()} onSuccess={vi.fn()} />)
    expect(unitLabel()).toContain('km')
    fireEvent.change(document.getElementById('date')!, { target: { value: '2026-03-01' } })
    fireEvent.change(document.getElementById('odometer_km')!, { target: { value: '50000' } })
    fireEvent.click(screen.getByRole('button', { name: 'common:create' }))
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalledTimes(1))
    expect(createMutateAsync.mock.calls[0][0].odometer_km).toBe(50000)
  })
})
