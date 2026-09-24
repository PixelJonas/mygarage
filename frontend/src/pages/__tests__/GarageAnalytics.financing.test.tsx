/**
 * Financing on the garage analytics page (ticket #9).
 *
 * Financing is part of every cost total, so the page has to show it wherever
 * the total is broken down: a summary card, a per-vehicle table column (so the
 * row adds up to its Total), a monthly-trend bar, and the CSV export.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import type { ReactNode } from 'react'

const captured = vi.hoisted(() => ({ charts: [] as unknown[] }))
vi.mock('recharts', () => {
  const Pass = ({ children }: { children?: ReactNode }) => <>{children}</>
  return {
    ResponsiveContainer: Pass,
    PieChart: Pass,
    Pie: Pass,
    Cell: () => null,
    ComposedChart: ({ data, children }: { data: unknown; children?: ReactNode }) => {
      captured.charts.push(data)
      return <>{children}</>
    },
    // `series:` prefix keeps this from colliding with any getByText on a label.
    Bar: ({ name }: { name?: string }) => <span data-testid="trend-bar">{`series:${name}`}</span>,
    Line: () => null,
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
    Legend: () => null,
  }
})

vi.mock('../../services/api', () => ({ default: { get: vi.fn() } }))
vi.mock('../../hooks/useCurrencyPreference', () => ({
  useCurrencyPreference: () => ({ currencyCode: 'USD', locale: 'en-US' }),
}))
vi.mock('../../hooks/useTimeFormat', () => ({ useTimeFormat: () => ({ timeFormat: '12h' }) }))
vi.mock('../../components/GarageAnalyticsHelpDrawer', () => ({ default: () => null }))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: () => Promise.resolve() },
  }),
  Trans: ({ children }: { children: ReactNode }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
}))

import api from '../../services/api'
import GarageAnalytics from '../GarageAnalytics'
import type { GarageAnalytics as GarageAnalyticsData } from '../../types/analytics'

const mockedGet = vi.mocked(api).get

const ZERO = '0.00'

function vehicle(
  vin: string,
  nickname: string,
  overrides: Partial<GarageAnalyticsData['cost_by_vehicle'][number]> = {}
): GarageAnalyticsData['cost_by_vehicle'][number] {
  return {
    vin,
    name: `2024 ${nickname}`,
    nickname,
    purchase_price: ZERO,
    total_maintenance: ZERO,
    total_upgrades: ZERO,
    total_inspection: ZERO,
    total_collision: ZERO,
    total_detailing: ZERO,
    total_fuel: ZERO,
    total_def: ZERO,
    total_insurance: ZERO,
    total_financing: ZERO,
    total_cost: ZERO,
    ...overrides,
  }
}

// Fuel 400 + financing 1,450 = 1,850 running cost for the leased van.
const GARAGE: GarageAnalyticsData = {
  vehicle_count: 2,
  total_costs: {
    total_garage_value: '0.00',
    total_maintenance: ZERO,
    total_upgrades: ZERO,
    total_inspection: ZERO,
    total_collision: ZERO,
    total_detailing: ZERO,
    total_fuel: '500.00',
    total_def: ZERO,
    total_insurance: ZERO,
    total_taxes: ZERO,
    total_financing: '1450.00',
  },
  cost_breakdown_by_category: [
    { category: 'Fuel', amount: '500.00' },
    { category: 'Financing', amount: '1450.00' },
  ],
  cost_by_vehicle: [
    vehicle('V1', 'Van', { total_fuel: '400.00', total_financing: '1450.00', total_cost: '1850.00' }),
    vehicle('V2', 'Bike', { total_fuel: '100.00', total_cost: '100.00' }),
  ],
  monthly_trends: [
    { month: 'Jan 2026', service: ZERO, fuel: '50.00', def_cost: ZERO, insurance: ZERO, financing: '450.00', total: '500.00' },
    { month: 'Feb 2026', service: ZERO, fuel: '50.00', def_cost: ZERO, insurance: ZERO, financing: '1000.00', total: '1050.00' },
  ],
}

const NO_FINANCING: GarageAnalyticsData = {
  ...GARAGE,
  total_costs: { ...GARAGE.total_costs, total_financing: ZERO },
  cost_breakdown_by_category: [{ category: 'Fuel', amount: '500.00' }],
  cost_by_vehicle: [vehicle('V1', 'Van', { total_fuel: '400.00', total_cost: '400.00' })],
  monthly_trends: [
    { month: 'Jan 2026', service: ZERO, fuel: '50.00', def_cost: ZERO, insurance: ZERO, financing: ZERO, total: '50.00' },
  ],
}

beforeEach(() => {
  captured.charts = []
  mockedGet.mockReset()
  mockedGet.mockResolvedValue({ data: GARAGE })
})

describe('GarageAnalytics — financing summary card', () => {
  it('shows a Financing card with the garage-wide financing total', async () => {
    render(<GarageAnalytics />)
    const card = (await screen.findByText('garage.cards.financing')).closest('div')!.parentElement!
    expect(within(card).getByText('$1,450.00')).toBeInTheDocument()
  })

  it('hides the Financing card when nothing is financed', async () => {
    mockedGet.mockResolvedValue({ data: NO_FINANCING })
    render(<GarageAnalytics />)
    await screen.findByText('garage.cards.fuel')
    expect(screen.queryByText('garage.cards.financing')).not.toBeInTheDocument()
  })
})

describe('GarageAnalytics — financing in the per-vehicle table', () => {
  it('has a Financing column so each row adds up to its Total', async () => {
    render(<GarageAnalytics />)
    await screen.findByText('garage.table.financing')

    const vanRow = screen.getAllByText('Van').map((el) => el.closest('tr')).find(Boolean)!
    const cells = within(vanRow).getAllByRole('cell').map((c) => c.textContent)
    // …Fuel, DEF, Financing, Total
    expect(cells.slice(-4)).toEqual(['$400.00', '$0.00', '$1,450.00', '$1,850.00'])
  })
})

describe('GarageAnalytics — financing in the monthly trend', () => {
  it('adds a Financing bar series', async () => {
    render(<GarageAnalytics />)
    await screen.findByText('garage.table.financing')
    const series = screen.getAllByTestId('trend-bar').map((el) => el.textContent)
    expect(series).toContain('series:garage.cards.financing')
  })

  it('includes financing in the chart data and in the rolling averages', async () => {
    render(<GarageAnalytics />)
    await screen.findByText('garage.table.financing')
    const trend = captured.charts.find(
      (d): d is Array<{ Financing?: number; avg3?: number }> =>
        Array.isArray(d) && d.length > 0 && typeof d[0] === 'object' && d[0] !== null && 'avg3' in d[0]
    )
    expect(trend).toBeDefined()
    expect(trend![0].Financing).toBe(450)
    expect(trend![1].Financing).toBe(1000)
    // Jan total = 50 fuel + 450 financing = 500; Feb 1,050 → trailing avg (500+1050)/2.
    expect(trend![0].avg3).toBe(500)
    expect(trend![1].avg3).toBe(775)
  })
})

describe('GarageAnalytics — financing in the category legend', () => {
  it('gives every category, including the tenth, its own colour', async () => {
    const CATEGORIES = [
      'Maintenance', 'Upgrades', 'Inspection', 'Collision', 'Detailing',
      'Fuel', 'DEF', 'Insurance', 'Taxes', 'Financing',
    ]
    mockedGet.mockResolvedValue({
      data: {
        ...GARAGE,
        cost_breakdown_by_category: CATEGORIES.map((category) => ({ category, amount: '10.00' })),
      },
    })
    render(<GarageAnalytics />)
    await screen.findByText('Financing')

    const swatchColor = (label: string) => {
      const swatch = screen.getByText(label).querySelector('span')!
      return swatch.style.backgroundColor
    }
    const colors = CATEGORIES.map(swatchColor)
    // A palette shorter than the category count wraps and repeats a colour,
    // making two slices indistinguishable.
    expect(new Set(colors).size).toBe(CATEGORIES.length)
  })
})

describe('GarageAnalytics — financing in the CSV export', () => {
  it('exports the financing total, the per-vehicle column and the monthly column', async () => {
    // ExportMenu is real here; read the blob out of the object-URL call.
    const blobs: Blob[] = []
    const createObjectURL = vi
      .spyOn(URL, 'createObjectURL')
      .mockImplementation((blob: Blob | MediaSource) => {
        blobs.push(blob as Blob)
        return 'blob:mock'
      })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    try {
      render(<GarageAnalytics />)
      await screen.findByText('garage.table.financing')
      fireEvent.click(screen.getByRole('button', { name: /export/i }))
      fireEvent.click(await screen.findByRole('menuitem', { name: 'CSV' }))
      await waitFor(() => expect(blobs).toHaveLength(1))
      const csv = await blobs[0].text()

      expect(csv).toContain('Financing,1450.00')
      expect(csv).toContain('Fuel,DEF,Financing,Running Costs')
      // purchase, maint, upgrades, inspection, collision, detailing, fuel, DEF, financing, total
      expect(csv).toContain('"2024 Van",0.00,0.00,0.00,0.00,0.00,0.00,400.00,0.00,1450.00,1850.00')
      expect(csv).toContain('Month,Service,Fuel,DEF,Financing,Total')
      expect(csv).toContain('Feb 2026,0.00,50.00,0.00,1000.00,1050.00')
    } finally {
      createObjectURL.mockRestore()
      click.mockRestore()
    }
  })
})
