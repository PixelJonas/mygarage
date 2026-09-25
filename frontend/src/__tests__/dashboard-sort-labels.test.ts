import { describe, it, expect } from 'vitest'
import { join } from 'node:path'
import { SUPPORTED_LANGUAGES } from '@/constants/i18n'
import { DASHBOARD_SORT_OPTIONS } from '@/constants/dashboardSort'
import { EN_DIR, LOCALES_DIR, loadJson } from '../../scripts/translation-utils'

/**
 * The dashboard's sort trigger reads `Sort: {{label}}` with the checked menu
 * item as the label, so a label names the order without a verb of its own:
 * "Sort by Name" read "Sort: Sort by Name" in every language.
 */
const dashboard = (file: string): Record<string, string> =>
  loadJson(file).dashboard as Record<string, string>

const en = dashboard(join(EN_DIR, 'vehicles.json'))
const sortKeys = DASHBOARD_SORT_OPTIONS.map((o) => o.labelKey.replace('vehicles:dashboard.', ''))
const translated = SUPPORTED_LANGUAGES.map((l) => l.code).filter((code) => code !== 'en')

describe('dashboard sort labels', () => {
  it.each(sortKeys)('%s names the order without repeating the trigger verb', (key) => {
    expect(en[key]).not.toMatch(/\bsort/i)
  })

  it.each(translated)('%s translates the trigger', (lang) => {
    const { sortTrigger } = dashboard(join(LOCALES_DIR, lang, 'vehicles.json'))
    expect(sortTrigger).not.toBe(en.sortTrigger)
  })
})
