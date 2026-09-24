/**
 * The order the dashboard's vehicle list opens in, and the order it shows.
 *
 * Each person saves a default order in Quick Settings (`users.dashboard_sort`,
 * or this browser when there is no account). The dashboard's sort menu
 * overrides it for the rest of the tab's session (#180), but only over the
 * default it was picked over: a new default, set here or on another device,
 * drops the pick.
 */

import { useEffect, useState } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { asDashboardSort, type DashboardSort } from '@/constants/dashboardSort'
import { forgetSortPick, readSortPick, rememberSortPick } from '@/utils/dashboardSort'
import { usePersonalPreference } from './usePersonalPreference'

/** The localStorage key the default is kept under when there is no account. */
export const DASHBOARD_SORT_STORAGE_KEY = 'dashboard_sort'

/** This person's default order: the account's, else this browser's, else Name. */
export function useDashboardSort(): { dashboardSort: DashboardSort } {
  return {
    dashboardSort: usePersonalPreference('dashboard_sort', DASHBOARD_SORT_STORAGE_KEY, asDashboardSort),
  }
}

/**
 * The order the dashboard shows: this tab's sort-menu pick while it still
 * stands over the current default, else the default.
 *
 * @returns The order, and the sort menu's writer.
 */
export function useDashboardSortOrder(): {
  sortBy: DashboardSort
  choose: (sort: DashboardSort) => void
} {
  const { user } = useAuth()
  const userId = user?.id
  const { dashboardSort } = useDashboardSort()
  const [pick, setPick] = useState(() => readSortPick(userId))

  // A pick made over another default is dropped from state before it renders,
  if (pick !== null && pick.over !== dashboardSort) setPick(null)
  // and from this tab's storage, or changing the default back and returning to
  // the dashboard would bring it back.
  useEffect(() => {
    const stored = readSortPick(userId)
    if (stored !== null && stored.over !== dashboardSort) forgetSortPick(userId)
  }, [dashboardSort, userId])

  const choose = (sort: DashboardSort): void => {
    const next = { sort, over: dashboardSort }
    setPick(next)
    rememberSortPick(userId, next)
  }

  return { sortBy: pick?.sort ?? dashboardSort, choose }
}
