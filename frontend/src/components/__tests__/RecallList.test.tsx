import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { Recall } from '../../types/recall'

const useRecallRecordsMock = vi.fn()
const deleteMutate = vi.fn()
const toggleMutate = vi.fn()
const nhtsaMutate = vi.fn()
const invalidateQueries = vi.fn()

vi.mock('../../hooks/queries/useRecallRecords', () => ({
  useRecallRecords: (...a: unknown[]) => useRecallRecordsMock(...a),
  useDeleteRecallRecord: () => ({ mutate: deleteMutate, isPending: false, variables: undefined }),
  useCheckNHTSA: () => ({ mutate: nhtsaMutate, isPending: false }),
  useToggleRecallResolved: () => ({ mutate: toggleMutate, isPending: false }),
}))
vi.mock('@tanstack/react-query', () => ({ useQueryClient: () => ({ invalidateQueries }) }))
vi.mock('../../services/api', () => ({ default: { get: vi.fn().mockResolvedValue({ data: { settings: [] } }) } }))
vi.mock('../../hooks/useDateLocale', () => ({ useDateLocale: () => 'en-US' }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import RecallList from '../RecallList'

const active = {
  id: 1, vin: 'V1', component: 'Airbag Inflator', nhtsa_campaign_number: '23V123000',
  summary: 'Inflator may rupture', consequence: '', remedy: '', notes: '',
  date_announced: '2026-02-01', is_resolved: false, resolved_at: null,
} as unknown as Recall

const onAddClick = vi.fn()
const onEditClick = vi.fn()
const PROPS = { vin: 'V1', onAddClick, onEditClick, onRefresh: vi.fn() }

beforeEach(() => {
  vi.clearAllMocks()
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  useRecallRecordsMock.mockReturnValue({ data: { recalls: [active], total: 1, active_count: 1, resolved_count: 0 }, isLoading: false, error: null })
})

describe('RecallList — rendering + row actions', () => {
  it('renders the component title and the NHTSA campaign identifier (fails if the title or the Mono campaign chip is dropped)', () => {
    render(<RecallList {...PROPS} />)
    expect(screen.getByText('Airbag Inflator')).toBeInTheDocument()
    expect(screen.getByText('23V123000')).toBeInTheDocument()
  })

  it('clicking Edit calls onEditClick with THE WHOLE recall (fails if edit is unwired or passes a truncated object)', () => {
    render(<RecallList {...PROPS} />)
    fireEvent.click(screen.getByRole('button', { name: 'common:edit' }))
    expect(onEditClick).toHaveBeenCalledWith(active)
  })

  it('clicking Delete (confirm accepted) calls the delete mutation with the recall id (fails if delete is unwired or the confirm gate is dropped)', () => {
    render(<RecallList {...PROPS} />)
    fireEvent.click(screen.getByRole('button', { name: 'common:delete' }))
    expect(window.confirm).toHaveBeenCalled()
    expect(deleteMutate).toHaveBeenCalledWith(1, expect.anything())
  })
})

describe('RecallList — mark-resolved toggles BOTH directions (status true AND false)', () => {
  it('an ACTIVE recall offers markResolved → toggles to isResolved:true (fails if the toggle target is inverted)', () => {
    render(<RecallList {...PROPS} />)
    fireEvent.click(screen.getByRole('button', { name: 'recallList.markResolved' }))
    expect(toggleMutate).toHaveBeenCalledWith({ recallId: 1, isResolved: true }, expect.anything())
  })

  it('a RESOLVED recall offers markActive → toggles to isResolved:false (fails if the false branch is missing or swapped)', () => {
    useRecallRecordsMock.mockReturnValue({ data: { recalls: [{ ...active, is_resolved: true, resolved_at: '2026-03-01' }], total: 1, active_count: 0, resolved_count: 1 }, isLoading: false, error: null })
    render(<RecallList {...PROPS} />)
    fireEvent.click(screen.getByRole('button', { name: 'recallList.markActive' }))
    expect(toggleMutate).toHaveBeenCalledWith({ recallId: 1, isResolved: false }, expect.anything())
  })
})

describe('RecallList — status filter + empty state + refresh wiring', () => {
  it('changing the status filter re-queries with the selected filter (fails if the select is unwired)', () => {
    render(<RecallList {...PROPS} />)
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'active' } })
    expect(useRecallRecordsMock).toHaveBeenLastCalledWith('V1', 'active')
  })

  it('with zero recalls, the "add manual entry" CTA fires onAddClick (fails if the two-CTA empty state is unwired)', () => {
    useRecallRecordsMock.mockReturnValue({ data: { recalls: [], total: 0, active_count: 0, resolved_count: 0 }, isLoading: false, error: null })
    render(<RecallList {...PROPS} />)
    expect(screen.getByText('recallList.noRecords')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'recallList.addManualEntry' }))
    expect(onAddClick).toHaveBeenCalled()
  })

  it('a recalls-refresh window event invalidates the recalls query (fails if the restyle disturbs the event subscription)', async () => {
    render(<RecallList {...PROPS} />)
    window.dispatchEvent(new Event('recalls-refresh'))
    await waitFor(() => expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['recalls', 'V1'] }))
  })
})

describe('RecallList — resolved timestamp', () => {
  it('renders the resolved date from the wire-shaped datetime (fails with "Invalid Date" if it is fed to the date-only formatter)', () => {
    // resolved_at is a backend datetime, serialised naive: no Z, no offset.
    useRecallRecordsMock.mockReturnValue({ data: { recalls: [{ ...active, is_resolved: true, resolved_at: '2026-03-01T12:00:00' }], total: 1, active_count: 0, resolved_count: 1 }, isLoading: false, error: null })
    render(<RecallList {...PROPS} />)
    expect(screen.getByText('Mar 1, 2026')).toBeInTheDocument()
    expect(screen.queryByText(/Invalid Date/)).toBeNull()
  })
})
