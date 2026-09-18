import { todayInHousehold } from '@/constants/i18n'
/**
 * Date utility functions to handle date formatting without timezone issues
 */

import { enUS, de, pl, ru, uk, ptBR } from 'date-fns/locale'
import type { Locale } from 'date-fns'
import { getActiveLocale } from '@/constants/i18n'

/**
 * date-fns locale for the active language.
 *
 * date-fns takes a locale OBJECT, not the Intl locale string that
 * useDateLocale()/getActiveLocale() return, so relative-time output
 * ("3 months ago") stayed English in every language until this existed.
 */
const DATE_FNS_LOCALES: Record<string, Locale> = {
  'en-US': enUS,
  'de-DE': de,
  'pl-PL': pl,
  'ru-RU': ru,
  'uk-UA': uk,
  'pt-BR': ptBR,
}

export function getDateFnsLocale(): Locale {
  return DATE_FNS_LOCALES[getActiveLocale()] ?? enUS
}

/**
 * Format a date string for display without timezone conversion.
 * Appends T00:00:00 to force local timezone interpretation.
 *
 * @param dateString - ISO date string (YYYY-MM-DD)
 * @param options - Intl.DateTimeFormatOptions for formatting
 * @param locale - Intl locale; defaults to the language selected in the app.
 *   It used to default to 'en-US', and 26 of the 34 call sites omit it — so
 *   most dates in the UI rendered US-English no matter the chosen language.
 * @returns Formatted date string
 */
export function formatDateForDisplay(
  dateString: string,
  options: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  },
  locale: string = getActiveLocale()
): string {
  // Parse date without timezone conversion by appending T00:00:00
  const date = new Date(dateString + 'T00:00:00')
  return date.toLocaleDateString(locale, options)
}

/**
 * Format a date string for input[type="date"] without timezone issues.
 * Ensures the date is in YYYY-MM-DD format without timezone conversion.
 *
 * @param dateString - Date string in various formats
 * @returns Date string in YYYY-MM-DD format
 */
export function formatDateForInput(dateString?: string | null): string {
  if (!dateString) {
    // The household's date, not the browser's (see todayInHousehold).
    return todayInHousehold()
  }

  // If it's already in YYYY-MM-DD format, return as-is
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateString)) {
    return dateString
  }

  // Otherwise parse and format without timezone conversion
  const date = new Date(dateString + 'T00:00:00')
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
