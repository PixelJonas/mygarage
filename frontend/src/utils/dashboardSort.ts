/**
 * The dashboard sort menu's pick for this tab, and the default it was picked
 * over (#180). `useDashboardSortOrder` holds the rules; this is the storage.
 *
 * `sessionStorage`, not `localStorage`: #180 asks for the pick to survive a
 * refresh "in the current login session", and a new tab or browser should open
 * on the default. Kept per user, so a household member who signs in on the same
 * tab gets their own default. Every access is guarded because storage throws in
 * a private window or with site data blocked.
 */

import { isDashboardSort, type DashboardSort } from '../constants/dashboardSort'

export interface SortPick {
  sort: DashboardSort
  over: DashboardSort
}

/** Where a user's pick is kept; `local` when there is no account. */
export function sortPickKey(userId: number | null | undefined): string {
  return `mygarage:dashboard:sortPick:${userId ?? 'local'}`
}

export function readSortPick(userId: number | null | undefined): SortPick | null {
  try {
    const raw = sessionStorage.getItem(sortPickKey(userId))
    if (raw === null) return null
    const { sort, over } = JSON.parse(raw) as Record<string, unknown>
    return isDashboardSort(sort) && isDashboardSort(over) ? { sort, over } : null
  } catch {
    // Unreadable, not JSON, or JSON null: the default is a perfectly good answer.
    return null
  }
}

export function rememberSortPick(userId: number | null | undefined, pick: SortPick): void {
  try {
    sessionStorage.setItem(sortPickKey(userId), JSON.stringify(pick))
  } catch {
    // Not remembering it is a smaller failure than breaking the sort.
  }
}

export function forgetSortPick(userId: number | null | undefined): void {
  try {
    sessionStorage.removeItem(sortPickKey(userId))
  } catch {
    // Nothing stored that we could reach, so nothing to forget.
  }
}
