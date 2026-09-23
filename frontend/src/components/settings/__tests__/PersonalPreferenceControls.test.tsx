/**
 * Time format, language and currency: each person's own display choices, now
 * in Quick Settings. With an account they save to it (`PUT /auth/me`); without
 * one (auth mode none) they live in this browser's localStorage. A failed save
 * puts the previous choice back.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const h = vi.hoisted(() => ({
  isAuthenticated: true,
  user: { time_format: '12h', language: 'en', currency_code: 'USD' } as Record<string, string> | null,
  refreshUser: vi.fn(),
  changeLanguage: vi.fn(),
}))

vi.mock('@/services/api', () => ({ default: { put: vi.fn() } }))

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ isAuthenticated: h.isAuthenticated, user: h.user, refreshUser: h.refreshUser }),
}))

vi.mock('react-i18next', () => {
  const t = (key: string): string => key
  const i18n = { language: 'en', changeLanguage: (lang: string) => h.changeLanguage(lang) }
  return {
    useTranslation: () => ({ t, i18n }),
    Trans: ({ children }: { children: React.ReactNode }) => children,
    initReactI18next: { type: '3rdParty', init: () => {} },
  }
})

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import api from '@/services/api'
import TimeFormatControl from '../TimeFormatControl'
import LanguageControl from '../LanguageControl'
import CurrencyControl from '../CurrencyControl'

const mockedPut = vi.mocked(api.put)

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  h.isAuthenticated = true
  h.user = { time_format: '12h', language: 'en', currency_code: 'USD' }
  h.refreshUser = vi.fn().mockResolvedValue(undefined)
  h.changeLanguage = vi.fn().mockResolvedValue(undefined)
  mockedPut.mockResolvedValue({ data: {} })
})

const pressed = (name: string): string | null =>
  screen.getByRole('button', { name }).getAttribute('aria-pressed')

describe('TimeFormatControl', () => {
  it('saves the choice to the account', async () => {
    render(<TimeFormatControl />)
    expect(pressed('timeFormat.twelveHour')).toBe('true')

    await userEvent.click(screen.getByRole('button', { name: 'timeFormat.twentyFourHour' }))

    expect(mockedPut).toHaveBeenCalledWith('/auth/me', { time_format: '24h' })
    expect(h.refreshUser).toHaveBeenCalled()
    expect(pressed('timeFormat.twentyFourHour')).toBe('true')
  })

  it('keeps the choice in this browser when there is no account', async () => {
    h.isAuthenticated = false
    h.user = null
    const keys: (string | null)[] = []
    const listen = (event: Event): void => {
      keys.push((event as StorageEvent).key)
    }
    window.addEventListener('storage', listen)
    render(<TimeFormatControl />)

    await userEvent.click(screen.getByRole('button', { name: 'timeFormat.twentyFourHour' }))
    window.removeEventListener('storage', listen)

    expect(localStorage.getItem('time_format')).toBe('24h')
    expect(mockedPut).not.toHaveBeenCalled()
    // Announced with its key: a keyless event also makes the unit-preference
    // store re-read and every unit consumer on the page re-render.
    expect(keys).toEqual(['time_format'])
  })

  it('puts the previous choice back when the save fails', async () => {
    mockedPut.mockRejectedValue(new Error('down'))
    render(<TimeFormatControl />)

    await userEvent.click(screen.getByRole('button', { name: 'timeFormat.twentyFourHour' }))

    await waitFor(() => expect(pressed('timeFormat.twelveHour')).toBe('true'))
  })
})

describe('LanguageControl', () => {
  it('switches the language at once and saves it to the account', async () => {
    render(<LanguageControl />)

    await userEvent.selectOptions(screen.getByLabelText('language.label'), 'pl')

    expect(h.changeLanguage).toHaveBeenCalledWith('pl')
    expect(mockedPut).toHaveBeenCalledWith('/auth/me', { language: 'pl' })
    expect(screen.getByLabelText('language.label')).toHaveValue('pl')
  })

  it('keeps the language in this browser when there is no account', async () => {
    h.isAuthenticated = false
    h.user = null
    render(<LanguageControl />)

    await userEvent.selectOptions(screen.getByLabelText('language.label'), 'de')

    expect(localStorage.getItem('i18nextLng')).toBe('de')
    expect(mockedPut).not.toHaveBeenCalled()
  })

  it('switches back when the save fails', async () => {
    mockedPut.mockRejectedValue(new Error('down'))
    render(<LanguageControl />)

    await userEvent.selectOptions(screen.getByLabelText('language.label'), 'pl')

    await waitFor(() => expect(screen.getByLabelText('language.label')).toHaveValue('en'))
    expect(h.changeLanguage).toHaveBeenLastCalledWith('en')
  })
})

describe('CurrencyControl', () => {
  it('asks in place before changing, then saves to the account', async () => {
    render(<CurrencyControl />)

    await userEvent.selectOptions(screen.getByLabelText('currency.label'), 'EUR')

    // Nothing saved yet, and the question is not a full-screen overlay: a
    // drawer cannot host one.
    expect(mockedPut).not.toHaveBeenCalled()
    expect(screen.getByText('currency.confirmMessage').closest('.fixed')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'currency.confirmAction' }))

    expect(mockedPut).toHaveBeenCalledWith('/auth/me', { currency_code: 'EUR' })
    expect(screen.getByLabelText('currency.label')).toHaveValue('EUR')
    expect(screen.queryByText('currency.confirmMessage')).toBeNull()
  })

  it('changes nothing when the question is cancelled', async () => {
    render(<CurrencyControl />)

    await userEvent.selectOptions(screen.getByLabelText('currency.label'), 'EUR')
    await userEvent.click(screen.getByRole('button', { name: 'common:cancel' }))

    expect(mockedPut).not.toHaveBeenCalled()
    expect(screen.getByLabelText('currency.label')).toHaveValue('USD')
  })

  it('keeps the currency in this browser when there is no account', async () => {
    h.isAuthenticated = false
    h.user = null
    render(<CurrencyControl />)

    await userEvent.selectOptions(screen.getByLabelText('currency.label'), 'EUR')
    await userEvent.click(screen.getByRole('button', { name: 'currency.confirmAction' }))

    expect(localStorage.getItem('currency_code')).toBe('EUR')
    expect(mockedPut).not.toHaveBeenCalled()
  })

  it('puts the previous currency back when the save fails', async () => {
    mockedPut.mockRejectedValue(new Error('down'))
    render(<CurrencyControl />)

    await userEvent.selectOptions(screen.getByLabelText('currency.label'), 'EUR')
    await userEvent.click(screen.getByRole('button', { name: 'currency.confirmAction' }))

    await waitFor(() => expect(screen.getByLabelText('currency.label')).toHaveValue('USD'))
  })
})
