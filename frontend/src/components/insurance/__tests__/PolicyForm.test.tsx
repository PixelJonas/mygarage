import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { render } from '../../../__tests__/test-utils'
import type { InsurancePDFParseResponse, InsurancePolicy } from '../../../types/insurance'

const createMutateAsync = vi.fn().mockResolvedValue({})
const updateMutateAsync = vi.fn().mockResolvedValue({})
const replaceMutateAsync = vi.fn().mockResolvedValue({})
vi.mock('../../../hooks/queries/useInsuranceRecords', () => ({
  useCreateInsurancePolicy: () => ({ mutateAsync: createMutateAsync }),
  useUpdateInsurancePolicy: () => ({ mutateAsync: updateMutateAsync }),
  useReplaceInsurancePolicy: () => ({ mutateAsync: replaceMutateAsync }),
}))
vi.mock('../../../hooks/queries/useQuickEntryVehicles', () => ({
  useQuickEntryVehicles: () => ({
    data: [
      { vin: 'RAMVIN00000000001', nickname: 'Ram', year: 2025, make: 'Ram', model: '3500', vehicle_type: 'Truck', thumbnail_url: null },
      { vin: 'MIRAGEVIN00000002', nickname: 'Mirage', year: 2017, make: 'Mitsubishi', model: 'Mirage', vehicle_type: 'Car', thumbnail_url: null },
    ],
  }),
}))
vi.mock('../../../hooks/useCurrencyPreference', () => ({
  useCurrencyPreference: () => ({ currencyCode: 'USD', locale: 'en-US', formatCurrency: vi.fn() }),
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

// The upload dialog is its own tested unit; here it is a button that hands
// back a canned parse, so the FORM's handling of that parse is what is tested.
let cannedParse: InsurancePDFParseResponse
vi.mock('../../InsurancePDFUpload', () => ({
  default: ({ onDataExtracted }: { onDataExtracted: (parsed: InsurancePDFParseResponse) => void }) => (
    <button type="button" onClick={() => onDataExtracted(cannedParse)}>
      fake-use-parse
    </button>
  ),
}))

import PolicyForm from '../PolicyForm'

beforeEach(() => vi.clearAllMocks())

const RAM = 'RAMVIN00000000001'
const MIRAGE = 'MIRAGEVIN00000002'

const fillPolicy = async (user: ReturnType<typeof userEvent.setup>, premium = '600') => {
  await user.type(screen.getByLabelText('insurance.provider *'), 'Progressive')
  await user.type(screen.getByLabelText('insurance.policyNumber *'), 'P-100')
  await user.type(screen.getByLabelText('common:startDate *'), '2026-01-01')
  await user.type(screen.getByLabelText('common:endDate *'), '2026-07-01')
  await user.type(screen.getByLabelText('insurance.policyPremium'), premium)
  await user.selectOptions(screen.getByLabelText('insurance.premiumFrequency'), 'Semi-Annual')
}

const addVehicle = async (user: ReturnType<typeof userEvent.setup>, vin: string, type: string, index: number) => {
  await user.selectOptions(screen.getByLabelText('insurance.addVehicle'), vin)
  await user.click(screen.getByRole('button', { name: 'common:add' }))
  await user.selectOptions(screen.getAllByLabelText('insurance.policyType *')[index], type)
}

const existing = (over: Partial<InsurancePolicy> = {}): InsurancePolicy => ({
  id: 7,
  provider: 'Progressive',
  policy_number: 'P-100',
  start_date: '2026-01-01',
  end_date: '2026-07-01',
  premium_amount: '600.00',
  premium_frequency: 'Semi-Annual',
  notes: null,
  status: 'active',
  previous_policy_id: null,
  has_successor: false,
  created_by_user_id: 1,
  created_at: null,
  fields: [{ label: 'Agent Phone', value: '555-0100' }],
  vehicles: [
    {
      id: 1, vin: RAM, vehicle_name: 'Ram', policy_type: 'Full Coverage', premium_share: '400.00',
      effective_share: '400.00', deductible: '500.00', coverage_limits: '100/300', notes: null,
      effective_to: null, fields: [{ label: 'Collision Deductible', value: '$500' }], can_edit: true,
    },
    {
      id: 2, vin: MIRAGE, vehicle_name: 'Mirage', policy_type: 'Liability', premium_share: '200.00',
      effective_share: '200.00', deductible: null, coverage_limits: null, notes: null,
      effective_to: null, fields: [], can_edit: true,
    },
  ],
  other_vehicle_count: 0,
  can_edit: true,
  ...over,
})

describe('PolicyForm — create', () => {
  it('submits the policy with every vehicle beneath it in ONE payload', async () => {
    const user = userEvent.setup()
    render(<PolicyForm mode="create" onClose={vi.fn()} onSuccess={vi.fn()} />)
    await fillPolicy(user)
    await addVehicle(user, RAM, 'Full Coverage', 0)
    await addVehicle(user, MIRAGE, 'Liability', 1)
    await user.type(screen.getAllByLabelText('insurance.vehicleShare')[0], '400')
    await user.type(screen.getAllByLabelText('insurance.deductible')[0], '500')

    await user.click(screen.getByRole('button', { name: 'common:create' }))

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalledTimes(1))
    expect(createMutateAsync).toHaveBeenCalledWith({
      provider: 'Progressive',
      policy_number: 'P-100',
      start_date: '2026-01-01',
      end_date: '2026-07-01',
      premium_amount: 600,
      premium_frequency: 'Semi-Annual',
      notes: null,
      fields: [],
      vehicles: [
        { vin: RAM, policy_type: 'Full Coverage', premium_share: 400, deductible: 500, coverage_limits: null, notes: null, fields: [] },
        // No share typed: null, so the backend splits what the Ram leaves.
        { vin: MIRAGE, policy_type: 'Liability', premium_share: null, deductible: null, coverage_limits: null, notes: null, fields: [] },
      ],
    })
    expect(updateMutateAsync).not.toHaveBeenCalled()
  })

  it("starts with the vehicle attached when opened from that vehicle's tab", () => {
    render(<PolicyForm mode="create" initialVin={MIRAGE} onClose={vi.fn()} onSuccess={vi.fn()} />)
    expect(screen.getByText('Mirage (2017 Mitsubishi Mirage)')).toBeInTheDocument()
    // Already attached, so it is no longer offered.
    const picker = screen.getByLabelText('insurance.addVehicle')
    expect(within(picker).queryByRole('option', { name: /Mirage/ })).not.toBeInTheDocument()
  })

  it('a suggested label is one tap, and is not offered twice', async () => {
    const user = userEvent.setup()
    render(<PolicyForm mode="create" onClose={vi.fn()} onSuccess={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: 'forms:insuranceFieldLabels.agentPhone' }))

    expect(screen.getByDisplayValue('forms:insuranceFieldLabels.agentPhone')).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'forms:insuranceFieldLabels.agentPhone' })
    ).not.toBeInTheDocument()
  })

  it('"use this data" from a parsed document fills the policy AND attaches its matched vehicles', async () => {
    const user = userEvent.setup()
    cannedParse = {
      success: true,
      data: {
        provider: 'Progressive', policy_number: 'P-PDF', policy_type: 'Full Coverage',
        start_date: '2026-01-01', end_date: '2026-07-01', premium_amount: '600.00',
        premium_frequency: 'Semi-Annual', deductible: null, coverage_limits: null, notes: null,
      },
      vehicles: [
        { vin: RAM, matched: true, vehicle_name: 'Ram', premium_share: '320.00', deductible: '500.00' },
        { vin: 'NOTINGARAGE000003', matched: false, vehicle_name: null, premium_share: '99.00', deductible: null },
      ],
      confidence: {}, confidence_score: 90, parser_used: 'progressive', warnings: [],
    }
    render(<PolicyForm mode="create" onClose={vi.fn()} onSuccess={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: 'insuranceForm.importFromPdf' }))
    await user.click(screen.getByRole('button', { name: 'fake-use-parse' }))
    await user.click(screen.getByRole('button', { name: 'common:create' }))

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalledTimes(1))
    const payload = createMutateAsync.mock.calls[0][0]
    expect(payload.policy_number).toBe('P-PDF')
    expect(payload.vehicles).toEqual([
      { vin: RAM, policy_type: 'Full Coverage', premium_share: 320, deductible: 500, coverage_limits: null, notes: null, fields: [] },
    ])
  })
})

describe('PolicyForm — allocation feedback', () => {
  it('shows the even split an empty share will resolve to, and warns when shares exceed the premium', async () => {
    const user = userEvent.setup()
    render(<PolicyForm mode="create" onClose={vi.fn()} onSuccess={vi.fn()} />)
    await fillPolicy(user, '600')
    await addVehicle(user, RAM, 'Full Coverage', 0)
    await addVehicle(user, MIRAGE, 'Liability', 1)

    // Nothing explicit: both vehicles take the even split.
    for (const input of screen.getAllByLabelText('insurance.vehicleShare')) {
      expect(input).toHaveAttribute('placeholder', 'insurance.evenSplit')
    }
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()

    await user.type(screen.getAllByLabelText('insurance.vehicleShare')[0], '700')
    expect(await screen.findByRole('alert')).toHaveTextContent('insurance.overAllocated')
  })

  it('warns when every share is fixed but they do not add up to the premium', async () => {
    const user = userEvent.setup()
    render(<PolicyForm mode="edit" policy={existing()} onClose={vi.fn()} onSuccess={vi.fn()} />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument() // 400 + 200 = 600

    const premium = screen.getByLabelText('insurance.policyPremium')
    await user.clear(premium)
    await user.type(premium, '700')
    expect(await screen.findByRole('alert')).toHaveTextContent('insurance.underAllocated')
  })
})

describe('PolicyForm — edit and replace', () => {
  it('edit sends the premium and the COMPLETE vehicle list together, keeping text it does not show', async () => {
    const user = userEvent.setup()
    render(<PolicyForm mode="edit" policy={existing()} onClose={vi.fn()} onSuccess={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: 'common:update' }))

    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalledTimes(1))
    const payload = updateMutateAsync.mock.calls[0][0]
    expect(payload.id).toBe(7)
    expect(payload.premium_amount).toBe(600)
    expect(payload.fields).toEqual([{ label: 'Agent Phone', value: '555-0100' }])
    expect(payload.vehicles).toEqual([
      {
        vin: RAM, policy_type: 'Full Coverage', premium_share: 400, deductible: 500,
        coverage_limits: '100/300', notes: null, effective_to: null,
        fields: [{ label: 'Collision Deductible', value: '$500' }],
      },
      {
        vin: MIRAGE, policy_type: 'Liability', premium_share: 200, deductible: null,
        coverage_limits: null, notes: null, effective_to: null, fields: [],
      },
    ])
  })

  it('never sends a vehicle list for a policy covering vehicles the user cannot see (it would remove them)', async () => {
    const user = userEvent.setup()
    render(
      <PolicyForm mode="edit" policy={existing({ other_vehicle_count: 1 })} onClose={vi.fn()} onSuccess={vi.fn()} />
    )
    expect(screen.getByText('insurance.vehiclesLocked')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'common:update' }))

    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalledTimes(1))
    expect(updateMutateAsync.mock.calls[0][0]).not.toHaveProperty('vehicles')
  })

  it('switching insurers starts blank, carries the vehicles, and posts to replace', async () => {
    const user = userEvent.setup()
    render(<PolicyForm mode="replace" policy={existing()} onClose={vi.fn()} onSuccess={vi.fn()} />)
    expect(screen.getByLabelText('insurance.provider *')).toHaveValue('')
    // The new term starts where the old one ends.
    expect(screen.getByLabelText('common:startDate *')).toHaveValue('2026-07-01')

    await user.type(screen.getByLabelText('insurance.provider *'), 'GEICO')
    await user.type(screen.getByLabelText('insurance.policyNumber *'), 'G-7')
    await user.type(screen.getByLabelText('common:endDate *'), '2027-01-01')
    await user.type(screen.getByLabelText('insurance.endOldOn'), '2026-06-15')
    await user.click(screen.getByRole('button', { name: 'common:create' }))

    await waitFor(() => expect(replaceMutateAsync).toHaveBeenCalledTimes(1))
    expect(replaceMutateAsync).toHaveBeenCalledWith({
      id: 7,
      provider: 'GEICO',
      policy_number: 'G-7',
      start_date: '2026-07-01',
      end_date: '2027-01-01',
      premium_amount: null,
      premium_frequency: 'Semi-Annual',
      notes: null,
      vins: [RAM, MIRAGE],
      end_old_on: '2026-06-15',
    })
    expect(createMutateAsync).not.toHaveBeenCalled()
  })
})
