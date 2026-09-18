/**
 * Form-level proof that new forms open on the HOUSEHOLD's date (plan 4.7),
 * not the browser's. Frozen instant 2026-09-17T11:00:00Z with the household
 * on Pacific/Kiritimati (UTC+14): the household's date is 2026-09-18 while
 * every plausible test host (UTC on CI, America/Chicago on dev boxes) still
 * says 2026-09-17 — so a form seeding from the browser clock fails here.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { screen } from '@testing-library/react'
import { render } from '../../__tests__/test-utils'
import { setHouseholdTimeZone } from '../../constants/i18n'

vi.mock('../../hooks/queries/useNotes', () => ({
  useCreateNote: () => ({ mutateAsync: vi.fn() }),
  useUpdateNote: () => ({ mutateAsync: vi.fn() }),
}))
vi.mock('../../hooks/queries/useTollRecords', () => ({
  useCreateTollTransaction: () => ({ mutateAsync: vi.fn() }),
  useUpdateTollTransaction: () => ({ mutateAsync: vi.fn() }),
}))
vi.mock('../../hooks/useCurrencyPreference', () => ({
  useCurrencyPreference: () => ({
    currencyCode: 'USD',
    locale: 'en-US',
    formatCurrency: vi.fn(),
  }),
}))

import NoteForm from '../NoteForm'
import TollTransactionForm from '../TollTransactionForm'

const HOUSEHOLD_DATE = '2026-09-18'

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers({ now: new Date('2026-09-17T11:00:00Z'), toFake: ['Date'] })
  setHouseholdTimeZone('Pacific/Kiritimati')
})

afterEach(() => {
  setHouseholdTimeZone(null)
  vi.useRealTimers()
})

describe('new forms default their date to the household day', () => {
  it('NoteForm opens dated in the household zone (fails if it seeds from the browser clock)', () => {
    render(<NoteForm vin="V1" onClose={vi.fn()} onSuccess={vi.fn()} />)
    expect(screen.getByLabelText('common:date *')).toHaveValue(HOUSEHOLD_DATE)
  })

  it('TollTransactionForm opens dated in the household zone', () => {
    render(<TollTransactionForm vin="V1" tollTags={[]} onClose={vi.fn()} onSuccess={vi.fn()} />)
    expect(screen.getByLabelText('common:date *')).toHaveValue(HOUSEHOLD_DATE)
  })
})
