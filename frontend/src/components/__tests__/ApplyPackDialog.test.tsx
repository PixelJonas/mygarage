/**
 * ApplyPackDialog — the preview is what gets applied.
 *
 * The dialog renders the backend's plan (history found, adoption, skip) and
 * turns the owner's anchor choices into the exact `anchors` map the apply
 * request carries. Nothing is written until Apply.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '../../__tests__/test-utils'
import { fireEvent } from '@testing-library/react'
import type { ApplyPackPreview } from '../../types/reminder'

const previewMock = vi.fn()
const applyMock = vi.fn()
vi.mock('../../hooks/useReminders', () => ({
  usePackPreview: (...args: unknown[]) => previewMock(...args),
  useApplyPack: () => ({ mutateAsync: applyMock, isPending: false }),
}))
vi.mock('../../hooks/useDateLocale', () => ({ useDateLocale: () => 'en-US' }))
vi.mock('../../hooks/useUnitPreference', async () => {
  const { METRIC_UNITS } = await import('@/__tests__/factories')
  return {
    useUnitPreference: () => ({ system: 'metric', showBoth: false, units: METRIC_UNITS, gallonStandard: 'us' }),
  }
})
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import ApplyPackDialog from '../ApplyPackDialog'

const preview: ApplyPackPreview = {
  pack_id: 'oil_and_filter',
  pack_name: 'Oil & Filter Service',
  items: [
    {
      key: 'oil_filter',
      maintenance_type: 'engine_oil_filter',
      title: 'Oil & Filter Change',
      interval_km: '8000',
      interval_months: 6,
      interval_days: null,
      interval_hours: null,
      rule_action: 'create',
      rule_id: null,
      skip_reason: null,
      keep_reminder_id: 4,
      adopted: true,
      supersede_reminder_ids: [8],
      anchor: {
        kind: 'service',
        date: '2026-06-13',
        odometer_km: '143063.89',
        hours: null,
        line_item_id: 60,
        origin: 'history',
        note: null,
      },
      newer_service: null,
      typed_history: [],
      untyped_candidates: [
        {
          line_item_id: 70,
          visit_id: 30,
          date: '2026-08-01',
          odometer_km: '144000',
          engine_hours: null,
          description: 'Oil change and air filter',
          maintenance_type: null,
        },
      ],
      due_date: '2026-12-13',
      due_mileage_km: '151063.89',
      due_hours: null,
      reminder_type: 'smart',
      note: null,
    },
    {
      key: 'drain_plug_washer',
      maintenance_type: 'drain_plug_washer',
      title: 'Inspect Drain Plug Washer',
      interval_km: null,
      interval_months: 6,
      interval_days: null,
      interval_hours: null,
      rule_action: 'skip',
      rule_id: null,
      skip_reason: 'two rules of this type exist on the vehicle',
      keep_reminder_id: null,
      adopted: false,
      supersede_reminder_ids: [],
      anchor: null,
      newer_service: null,
      typed_history: [],
      untyped_candidates: [],
      due_date: null,
      due_mileage_km: null,
      due_hours: null,
      reminder_type: null,
      note: null,
    },
  ],
}

function renderDialog() {
  const onApplied = vi.fn()
  render(
    <ApplyPackDialog vin="V1" packId="oil_and_filter" packName="Oil & Filter Service" onClose={vi.fn()} onApplied={onApplied} />,
  )
  return { onApplied }
}

beforeEach(() => {
  vi.clearAllMocks()
  previewMock.mockReturnValue({ data: preview, isLoading: false, error: null })
  applyMock.mockResolvedValue([])
})

describe('ApplyPackDialog', () => {
  it('shows the history found, the adoption and the due values from the preview, and the skipped item', () => {
    renderDialog()
    expect(screen.getByText('applyPack.historyFound')).toBeInTheDocument()
    expect(screen.getByText(/Jun 13, 2026/)).toBeInTheDocument()
    expect(screen.getByText(/applyPack\.adopts/)).toBeInTheDocument()
    expect(screen.getByText(/applyPack\.supersedes/)).toBeInTheDocument()
    expect(screen.getByText(/151,064 km/)).toBeInTheDocument()
    expect(screen.getByText('applyPack.skipTwoRules')).toBeInTheDocument()
    expect(screen.getByText('applyPack.ruleAction.skip')).toBeInTheDocument()
  })

  it('applies with NO anchors when the proposal is kept', async () => {
    const { onApplied } = renderDialog()
    fireEvent.click(screen.getByRole('button', { name: 'reminderList.applyPack' }))
    await waitFor(() => expect(applyMock).toHaveBeenCalledTimes(1))
    expect(applyMock.mock.calls[0][0]).toStrictEqual({
      packId: 'oil_and_filter',
      anchors: {},
      // Empty, not seeded from the preview: an item nobody typed in must keep
      // the pack's value, and a seeded override would silently overwrite the
      // destination vehicle's own intervals on every apply.
      overrides: {},
    })
    expect(onApplied).toHaveBeenCalled()
  })

  it('choosing an untyped line item sends its id, which the backend types', async () => {
    renderDialog()
    fireEvent.click(screen.getByLabelText(/applyPack\.choiceLineItem/))
    // The choice re-runs the preview with the anchors it will apply with.
    expect(previewMock.mock.calls.at(-1)?.[2]).toStrictEqual({ oil_filter: { done_today: false, line_item_id: 70 } })
    fireEvent.click(screen.getByRole('button', { name: 'reminderList.applyPack' }))
    await waitFor(() => expect(applyMock).toHaveBeenCalledTimes(1))
    expect(applyMock.mock.calls[0][0]).toStrictEqual({
      packId: 'oil_and_filter',
      anchors: { oil_filter: { done_today: false, line_item_id: 70 } },
      overrides: {},
    })
  })

  it('"treat as done today" sends done_today for that item only', async () => {
    renderDialog()
    fireEvent.click(screen.getByLabelText('applyPack.choiceDoneToday'))
    fireEvent.click(screen.getByRole('button', { name: 'reminderList.applyPack' }))
    await waitFor(() => expect(applyMock).toHaveBeenCalledTimes(1))
    expect(applyMock.mock.calls[0][0].anchors).toStrictEqual({ oil_filter: { done_today: true } })
  })

  it('after "done today" the choices stay visible and the proposal can be restored (codex FE R1-M1)', async () => {
    const oil = preview.items[0]
    const completionPlan: ApplyPackPreview = {
      ...preview,
      items: [{
        ...oil,
        untyped_candidates: [],
        anchor: { kind: 'completion', date: '2026-09-17', odometer_km: '150000', hours: null, line_item_id: null, origin: 'reminder', note: 'treated as done today at the current readings' },
      }],
    }
    const proposalPlan: ApplyPackPreview = { ...completionPlan, items: [{ ...oil, untyped_candidates: [] }] }
    previewMock.mockImplementation((_vin: unknown, _pack: unknown, anchors: Record<string, unknown>) => ({
      data: anchors.oil_filter ? completionPlan : proposalPlan, isLoading: false, error: null,
    }))
    renderDialog()
    fireEvent.click(screen.getByLabelText('applyPack.choiceDoneToday'))
    fireEvent.click(screen.getByLabelText('applyPack.choiceProposed'))
    fireEvent.click(screen.getByRole('button', { name: 'reminderList.applyPack' }))
    await waitFor(() => expect(applyMock).toHaveBeenCalledTimes(1))
    expect(applyMock.mock.calls[0][0].anchors).toStrictEqual({})
  })

  it('a failed apply shows the error and does not close', async () => {
    applyMock.mockRejectedValue(new Error('boom'))
    const { onApplied } = renderDialog()
    fireEvent.click(screen.getByRole('button', { name: 'reminderList.applyPack' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(onApplied).not.toHaveBeenCalled()
  })
})
