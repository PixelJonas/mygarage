import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { render } from '../../__tests__/test-utils'
import type { FinancingRecord } from '../../types/financing'

const createMutateAsync = vi.fn().mockResolvedValue({})
const updateMutateAsync = vi.fn().mockResolvedValue({})
vi.mock('../../hooks/queries/useFinancingRecords', () => ({
  useCreateFinancingRecord: () => ({ mutateAsync: createMutateAsync }),
  useUpdateFinancingRecord: () => ({ mutateAsync: updateMutateAsync }),
}))
vi.mock('../../hooks/useCurrencyPreference', () => ({ useCurrencyPreference: () => ({ currencyCode: 'USD', locale: 'en-US', formatCurrency: vi.fn() }) }))
// VendorSearch fetches vendors; stub it.
vi.mock('../VendorSearch', () => ({ default: () => <div data-testid="vendor-search" /> }))

import FinancingRecordForm from '../FinancingRecordForm'

beforeEach(() => vi.clearAllMocks())

describe('FinancingRecordForm — routing + exact payload (SDQ-C)', () => {
  it('create submits the COMPLETE payload INCLUDING vin (amount coerced to a number), and NEVER calls update (fails if a field is dropped, vin is omitted, the amount stays a string, or it misroutes)', async () => {
    const user = userEvent.setup()
    render(<FinancingRecordForm vin="V1" onClose={vi.fn()} onSuccess={vi.fn()} />)
    await user.clear(screen.getByLabelText('financing.date *'))
    await user.type(screen.getByLabelText('financing.date *'), '2026-03-01')
    await user.selectOptions(screen.getByLabelText('financing.category *'), 'lease_payment')
    await user.clear(screen.getByLabelText('common:amount *'))
    await user.type(screen.getByLabelText('common:amount *'), '450.00')
    await user.clear(screen.getByLabelText('common:notes'))
    await user.type(screen.getByLabelText('common:notes'), 'note')
    await user.click(screen.getByRole('button', { name: 'common:create' }))
    await waitFor(() => expect(createMutateAsync).toHaveBeenCalledTimes(1))
    const payload = createMutateAsync.mock.calls[0][0]
    expect(payload).toStrictEqual({
      vin: 'V1',
      date: '2026-03-01',
      category: 'lease_payment',
      amount: 450,
      vendor_id: undefined,
      notes: 'note',
    })
    expect(payload).toHaveProperty('vin')
    expect(updateMutateAsync).not.toHaveBeenCalled()
  })

  it('edit submits the UPDATE payload — routing id + vin + edited amount — and NEVER calls create (fails if it misroutes or drops the id/vin)', async () => {
    const record = {
      id: 6, date: '2026-01-10', category: 'loan_payment', amount: 300, vendor_id: 9, notes: 'y',
    } as unknown as FinancingRecord
    const user = userEvent.setup()
    render(<FinancingRecordForm vin="V1" record={record} onClose={vi.fn()} onSuccess={vi.fn()} />)
    await user.clear(screen.getByLabelText('common:amount *'))
    await user.type(screen.getByLabelText('common:amount *'), '325.50')
    await user.click(screen.getByRole('button', { name: 'common:update' }))
    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalledTimes(1))
    const payload = updateMutateAsync.mock.calls[0][0]
    expect(payload).toStrictEqual({
      id: 6,
      vin: 'V1',
      date: '2026-01-10',
      category: 'loan_payment',
      amount: 325.5,
      vendor_id: 9,
      notes: 'y',
    })
    expect(payload).toHaveProperty('vin')
    expect(createMutateAsync).not.toHaveBeenCalled()
  })

  it('the Field labels resolve to the controls carrying the expected ids (fails if a Field htmlFor/id association is dropped — including the currency carve-out)', () => {
    render(<FinancingRecordForm vin="V1" onClose={vi.fn()} onSuccess={vi.fn()} />)
    expect(screen.getByLabelText('common:amount *')).toHaveAttribute('id', 'amount')
    expect(screen.getByLabelText('financing.date *')).toHaveAttribute('id', 'date')
    expect(screen.getByLabelText('financing.category *')).toHaveAttribute('id', 'category')
  })

  it('labels the vendor picker "Lender", not "Vendor" (fails if the relabel regresses)', () => {
    render(<FinancingRecordForm vin="V1" onClose={vi.fn()} onSuccess={vi.fn()} />)
    expect(screen.getByText('financing.lender')).toBeInTheDocument()
  })
})

describe('FinancingRecordForm — required category', () => {
  it('rejects submission with no category selected (fails if category is left optional)', async () => {
    const user = userEvent.setup()
    render(<FinancingRecordForm vin="V1" onClose={vi.fn()} onSuccess={vi.fn()} />)
    await user.clear(screen.getByLabelText('financing.date *'))
    await user.type(screen.getByLabelText('financing.date *'), '2026-03-01')
    await user.clear(screen.getByLabelText('common:amount *'))
    await user.type(screen.getByLabelText('common:amount *'), '100')
    await user.click(screen.getByRole('button', { name: 'common:create' }))

    await waitFor(() =>
      expect(screen.getByText('common:validation.financing.categoryRequired')).toBeInTheDocument()
    )
    expect(createMutateAsync).not.toHaveBeenCalled()
  })
})

describe('FinancingRecordForm — amount field on NumberInput (Task 8 convention)', () => {
  it('is a textbox, not a spinbutton, and accepts a comma decimal', async () => {
    const user = userEvent.setup()
    render(<FinancingRecordForm vin="V1" onClose={vi.fn()} onSuccess={vi.fn()} />)
    const amountInput = screen.getByLabelText('common:amount *')
    expect(amountInput).toHaveAttribute('type', 'text')
    expect(screen.getByRole('textbox', { name: 'common:amount *' })).toBe(amountInput)

    await user.clear(screen.getByLabelText('financing.date *'))
    await user.type(screen.getByLabelText('financing.date *'), '2026-03-01')
    await user.selectOptions(screen.getByLabelText('financing.category *'), 'lease_payment')
    await user.type(amountInput, '450,00')
    await user.click(screen.getByRole('button', { name: 'common:create' }))

    await waitFor(() => expect(createMutateAsync).toHaveBeenCalledTimes(1))
    expect(createMutateAsync.mock.calls[0][0]).toMatchObject({ amount: 450 })
  })

  it('rejects unparseable text instead of silently discarding it', async () => {
    const user = userEvent.setup()
    render(<FinancingRecordForm vin="V1" onClose={vi.fn()} onSuccess={vi.fn()} />)
    await user.clear(screen.getByLabelText('financing.date *'))
    await user.type(screen.getByLabelText('financing.date *'), '2026-03-01')
    await user.selectOptions(screen.getByLabelText('financing.category *'), 'lease_payment')
    await user.type(screen.getByLabelText('common:amount *'), 'abc')
    await user.click(screen.getByRole('button', { name: 'common:create' }))

    await waitFor(() =>
      expect(screen.getByText('common:validation.amount.invalid')).toBeInTheDocument()
    )
    expect(createMutateAsync).not.toHaveBeenCalled()
  })
})
