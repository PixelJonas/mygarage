/**
 * todayInHousehold(): the browser's second "today" follows the household zone.
 *
 * Frozen instant 2026-09-17T02:00:00Z: UTC's calendar date (09-17) disagrees
 * with America/Chicago's (09-16, 21:00 the evening before). Assertions pin
 * explicit zones so they hold on any host zone (dev boxes run Central, CI
 * runs UTC).
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import {
  getHouseholdTimeZone,
  setHouseholdTimeZone,
  todayInHousehold,
} from '../../constants/i18n'
import { formatDateForInput } from '../dateUtils'

beforeEach(() => {
  vi.useFakeTimers({ now: new Date('2026-09-17T02:00:00Z') })
  setHouseholdTimeZone(null)
})

afterEach(() => {
  setHouseholdTimeZone(null)
  vi.useRealTimers()
})

describe('todayInHousehold', () => {
  it('returns the household date, both directions across the midnight gap', () => {
    setHouseholdTimeZone('UTC')
    expect(todayInHousehold()).toBe('2026-09-17')
    setHouseholdTimeZone('America/Chicago')
    expect(todayInHousehold()).toBe('2026-09-16')
  })

  it('an invalid zone from the server falls back to the browser zone instead of throwing', () => {
    setHouseholdTimeZone('Not/AZone')
    const browserToday = new Intl.DateTimeFormat('en-CA', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(new Date())
    expect(todayInHousehold()).toBe(browserToday)
  })

  it('an empty or null store means "not set", and the browser zone applies', () => {
    setHouseholdTimeZone('  ')
    expect(getHouseholdTimeZone()).toBeNull()
    expect(todayInHousehold()).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})

describe('formatDateForInput', () => {
  it('with no argument returns the HOUSEHOLD date, not the browser date', () => {
    setHouseholdTimeZone('America/Chicago')
    expect(formatDateForInput()).toBe('2026-09-16')
    setHouseholdTimeZone('UTC')
    expect(formatDateForInput()).toBe('2026-09-17')
  })

  it('with an argument it is unchanged: the given date passes through', () => {
    setHouseholdTimeZone('America/Chicago')
    expect(formatDateForInput('2026-01-05')).toBe('2026-01-05')
  })
})
