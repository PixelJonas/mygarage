import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '../../__tests__/test-utils'
import { fireEvent } from '@testing-library/react'
import api from '../../services/api'

vi.mock('../../services/api', () => ({ default: { get: vi.fn() } }))
vi.mock('../../hooks/useCurrencyPreference', () => ({
  useCurrencyPreference: () => ({ currencyCode: 'USD', locale: 'en-US', formatCurrency: (v: unknown) => String(v) }),
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const apiGet = api.get as unknown as ReturnType<typeof vi.fn>

import ReportsPanel from '../ReportsPanel'

beforeEach(() => {
  vi.clearAllMocks()
  Object.defineProperty(window.URL, 'createObjectURL', { value: vi.fn(() => 'blob:x'), writable: true, configurable: true })
  Object.defineProperty(window.URL, 'revokeObjectURL', { value: vi.fn(), writable: true, configurable: true })
  // jsdom cannot navigate to the blob: URL a download anchor points at, and
  // logs "Not implemented: navigation to another Document" on every click.
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
})

describe('ReportsPanel — report generation URLs (SDQ-C, five-action matrix)', () => {
  // Only the service-history reports read the date range — typing the start date via getByLabelText proves BOTH
  // the <Field> label association (RED→GREEN) and that Generate button [0] is the service-history report. The
  // year-based reports (cost-summary / tax-deduction / all-records) use the component's selectedYear default
  // (= new Date().getFullYear()), so their tests read the same expression rather than hard-coding a year.

  it('the service-history PDF button GETs the exact PDF URL (typed start date + currency/locale, no year) as a blob (fails if the date input is unwired, the endpoint is wrong, or a param is dropped/added)', async () => {
    apiGet.mockResolvedValue({ data: new Blob(['x'], { type: 'application/pdf' }) })
    render(<ReportsPanel vin="V1" />)
    fireEvent.change(screen.getByLabelText('reports.startDate'), { target: { value: '2026-01-01' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'reports.downloadPdf' })[0])
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(1))
    // strict 2-element call-array — extra/dropped params or a wrong endpoint fail toStrictEqual (never expect.anything())
    expect(apiGet.mock.calls[0]).toStrictEqual([
      '/vehicles/V1/reports/service-history-pdf?start_date=2026-01-01&currency_code=USD&locale=en-US',
      { responseType: 'blob' },
    ])
  })

  it('the cost-summary PDF button GETs the exact PDF URL (year = current year + currency/locale) as a blob (fails if cost-summary is routed to the wrong endpoint/handler or drops the year/currency params)', async () => {
    apiGet.mockResolvedValue({ data: new Blob(['x'], { type: 'application/pdf' }) })
    render(<ReportsPanel vin="V1" />)
    const year = new Date().getFullYear()
    fireEvent.click(screen.getAllByRole('button', { name: 'reports.downloadPdf' })[1])
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(1))
    expect(apiGet.mock.calls[0]).toStrictEqual([
      `/vehicles/V1/reports/cost-summary-pdf?year=${year}&currency_code=USD&locale=en-US`,
      { responseType: 'blob' },
    ])
  })

  it('the tax-deduction PDF button GETs the exact PDF URL (year = current year + currency/locale) as a blob (fails if tax-deduction is routed to the wrong endpoint/handler or drops the year/currency params)', async () => {
    apiGet.mockResolvedValue({ data: new Blob(['x'], { type: 'application/pdf' }) })
    render(<ReportsPanel vin="V1" />)
    const year = new Date().getFullYear()
    fireEvent.click(screen.getAllByRole('button', { name: 'reports.downloadPdf' })[2])
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(1))
    expect(apiGet.mock.calls[0]).toStrictEqual([
      `/vehicles/V1/reports/tax-deduction-pdf?year=${year}&currency_code=USD&locale=en-US`,
      { responseType: 'blob' },
    ])
  })

  it('the service-history CSV button GETs the exact CSV URL (typed start date, trailing &, no year/currency) as a blob (fails if the CSV endpoint is wrong or the date is dropped)', async () => {
    apiGet.mockResolvedValue({ data: new Blob(['x']) })
    render(<ReportsPanel vin="V1" />)
    fireEvent.change(screen.getByLabelText('reports.startDate'), { target: { value: '2026-01-01' } })
    fireEvent.click(screen.getAllByRole('button', { name: 'reports.exportCsv' })[0])
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(1))
    // CSV handler builds the query by hand: `service-history-csv?` + `start_date=2026-01-01&` (endDate empty → not appended)
    expect(apiGet.mock.calls[0]).toStrictEqual([
      '/vehicles/V1/reports/service-history-csv?start_date=2026-01-01&',
      { responseType: 'blob' },
    ])
  })

  it('the all-records CSV button GETs the exact CSV URL (year = current year) as a blob (fails if export is unwired or the endpoint/year is wrong)', async () => {
    apiGet.mockResolvedValue({ data: new Blob(['x']) })
    render(<ReportsPanel vin="V1" />)
    const year = new Date().getFullYear()
    fireEvent.click(screen.getAllByRole('button', { name: 'reports.exportCsv' })[1])
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(1))
    expect(apiGet.mock.calls[0]).toStrictEqual([`/vehicles/V1/reports/all-records-csv?year=${year}`, { responseType: 'blob' }])
  })
})
