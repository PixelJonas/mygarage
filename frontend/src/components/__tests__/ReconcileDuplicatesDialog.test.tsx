/**
 * ReconcileDuplicatesDialog — the owner keeps one reminder and the rest are
 * superseded; the request names exactly those ids.
 *
 * Imperial account: each member's due line is composed through the resolved
 * distance adapter, so a canonical 151064.24 km renders as "93,867 mi"
 * (151064.24 / 1.609344 = 93,866.94), never as a bare kilometre figure.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '../../__tests__/test-utils'
import { fireEvent } from '@testing-library/react'
import type { DuplicateGroup, Reminder } from '../../types/reminder'

const reconcileMock = vi.fn()
const pendingMock = vi.fn()
vi.mock('../../hooks/useReminders', () => ({
  useReconcileDuplicates: () => ({ mutateAsync: reconcileMock, isPending: false }),
  useReminders: (...args: unknown[]) => pendingMock(...args),
}))
vi.mock('../../hooks/useDateLocale', () => ({ useDateLocale: () => 'en-US' }))
vi.mock('../../hooks/useUnitPreference', async () => {
  const { IMPERIAL_UNITS } = await import('@/__tests__/factories')
  return {
    useUnitPreference: () => ({ system: 'imperial', showBoth: false, units: IMPERIAL_UNITS, gallonStandard: 'us' }),
  }
})
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import ReconcileDuplicatesDialog from '../ReconcileDuplicatesDialog'

const base = {
  vin: 'V1', reminder_type: 'both', status: 'pending', due_hours: null, notes: null,
  last_notified_at: null, created_at: '2026-06-14T00:00:00Z', updated_at: '2026-06-14T00:00:00Z',
}
const ruled = {
  ...base, id: 4, title: 'Oil Change', due_date: '2026-12-13', due_mileage_km: '151064.24', line_item_id: 60,
  rule_id: 1, rule: { id: 1, title: 'Oil Change', maintenance_type: 'engine_oil_filter', is_active: true },
} as unknown as Reminder
const loose = {
  ...base, id: 8, title: 'Oil & Filter Change', due_date: '2027-01-02', due_mileage_km: '153000', line_item_id: null,
  rule_id: null, rule: null,
} as unknown as Reminder

const group: DuplicateGroup = {
  maintenance_type: 'engine_oil_filter',
  label: 'Engine oil and filter',
  reminder_ids: [4, 8],
  suggested_keep_id: 4,
}

function renderDialog() {
  const onDone = vi.fn()
  render(
    <ReconcileDuplicatesDialog vin="V1" group={group} onClose={vi.fn()} onDone={onDone} />,
  )
  return { onDone }
}

beforeEach(() => {
  vi.clearAllMocks()
  reconcileMock.mockResolvedValue([ruled, loose])
  pendingMock.mockReturnValue({ data: [ruled, loose], isLoading: false })
})

describe('ReconcileDuplicatesDialog', () => {
  it('lists every member with its due line in the account distance unit and pre-selects the suggested keeper', () => {
    renderDialog()
    // 151064.24 km = 93,866.94 mi; 153000 km = 95,069.9 mi. Neither figure
    // may appear as kilometres.
    expect(screen.getByText(/93,867 mi/)).toBeInTheDocument()
    expect(screen.getByText(/95,070 mi/)).toBeInTheDocument()
    expect(screen.queryByText(/151,064/)).not.toBeInTheDocument()
    expect(screen.getByText(/Dec 13, 2026/)).toBeInTheDocument()
    expect(screen.getByText('duplicates.recurring')).toBeInTheDocument()
    expect(screen.getByText('duplicates.oneOff')).toBeInTheDocument()
    const keepRuled = screen.getByRole('radio', { name: /Oil Change/ }) as HTMLInputElement
    expect(keepRuled.checked).toBe(true)
  })

  it('confirming supersedes every member except the keeper and closes', async () => {
    const { onDone } = renderDialog()
    fireEvent.click(screen.getByRole('button', { name: 'duplicates.confirm' }))
    await waitFor(() => expect(reconcileMock).toHaveBeenCalledTimes(1))
    expect(reconcileMock.mock.calls[0][0]).toStrictEqual({ keepId: 4, supersedeIds: [8] })
    expect(onDone).toHaveBeenCalled()
  })

  it('choosing the other member makes it the keeper', async () => {
    renderDialog()
    fireEvent.click(screen.getByRole('radio', { name: /Oil & Filter Change/ }))
    fireEvent.click(screen.getByRole('button', { name: 'duplicates.confirm' }))
    await waitFor(() => expect(reconcileMock).toHaveBeenCalledTimes(1))
    expect(reconcileMock.mock.calls[0][0]).toStrictEqual({ keepId: 8, supersedeIds: [4] })
  })

  it('reads the PENDING reminders itself, whatever tab the list is on (codex FE R1-H3)', () => {
    renderDialog()
    expect(pendingMock).toHaveBeenCalledWith('V1', 'pending')
  })

  it('refuses to confirm while any member of the group is not loaded', () => {
    pendingMock.mockReturnValue({ data: [ruled], isLoading: false })
    renderDialog()
    expect(screen.getByRole('button', { name: 'duplicates.confirm' })).toBeDisabled()
    expect(screen.getByText('duplicates.incomplete')).toBeInTheDocument()
  })

  it('a failed request shows the error and does not close', async () => {
    reconcileMock.mockRejectedValue(new Error('boom'))
    const { onDone } = renderDialog()
    fireEvent.click(screen.getByRole('button', { name: 'duplicates.confirm' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(onDone).not.toHaveBeenCalled()
  })
})
