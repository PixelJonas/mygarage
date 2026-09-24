/**
 * Hook to access the user's time-format preference (12-hour vs 24-hour clock).
 *
 * Read through `usePersonalPreference`: the account's value when signed in,
 * else this browser's copy (kept live by the `storage` event a browser-only
 * save fires), else '12h' (matches the app's US-leaning defaults, e.g.
 * imperial units).
 */

import { usePersonalPreference } from './usePersonalPreference'

export type TimeFormat = '12h' | '24h'

/**
 * Narrow an unvalidated time-format string.
 *
 * `users.time_format` is a plain VARCHAR, so the generated schema types it as
 * `string`. Anything that is not exactly '24h' renders on a 12-hour clock,
 * which is also the app default.
 *
 * @param value A stored or transmitted preference, possibly absent.
 * @returns The narrowed preference.
 */
export function asTimeFormat(value: string | null | undefined): TimeFormat {
  return value === '24h' ? '24h' : '12h'
}

/**
 * Get the user's time-format preference from AuthContext or localStorage.
 *
 * @returns Object containing timeFormat ('12h' | '24h')
 *
 * @example
 * const { timeFormat } = useTimeFormat()
 * const label = formatTime(session.started_at, timeFormat)
 */
export function useTimeFormat(): { timeFormat: TimeFormat } {
  return { timeFormat: usePersonalPreference('time_format', 'time_format', asTimeFormat) }
}
