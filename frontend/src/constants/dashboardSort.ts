/**
 * The orders the dashboard's vehicle list can open in.
 *
 * Mirrors `SUPPORTED_DASHBOARD_SORTS` in the backend's
 * `app/constants/dashboard.py`; keep the two in sync when adding or removing an
 * order.
 */

/** Menu and Quick Settings labels, in menu order. */
export const DASHBOARD_SORT_OPTIONS = [
  { value: 'name', labelKey: 'vehicles:dashboard.sortByName' },
  { value: 'year-new', labelKey: 'vehicles:dashboard.newestFirst' },
  { value: 'year-old', labelKey: 'vehicles:dashboard.oldestFirst' },
  { value: 'maintenance', labelKey: 'vehicles:dashboard.byMaintenance' },
] as const

export type DashboardSort = (typeof DASHBOARD_SORT_OPTIONS)[number]['value']

export const DEFAULT_DASHBOARD_SORT: DashboardSort = 'name'

export function isDashboardSort(value: unknown): value is DashboardSort {
  return DASHBOARD_SORT_OPTIONS.some((option) => option.value === value)
}

/**
 * Narrow a stored default. `users.dashboard_sort` outlives deploys, so an
 * order since renamed or removed opens on Name rather than on a list no menu
 * item matches.
 */
export function asDashboardSort(value: string | null | undefined): DashboardSort {
  return isDashboardSort(value) ? value : DEFAULT_DASHBOARD_SORT
}
