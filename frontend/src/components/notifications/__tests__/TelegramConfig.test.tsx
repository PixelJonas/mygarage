/**
 * Fuel commands live with the bot they use (they were the Telegram Fuel Bot
 * card under Settings > Integrations). The server answers them only while
 * Telegram is on, so the switch follows the Telegram switch here. Loading and
 * saving the switch is covered by SettingsNotificationsTab.test.tsx.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

import { TelegramConfig } from '../TelegramConfig'

const FUEL = { name: 'telegram.fuel.enable' }

function renderConfig(settings: Record<string, string>): void {
  render(
    <TelegramConfig
      settings={settings}
      onSettingChange={vi.fn()}
      onTextChange={vi.fn()}
      onTest={vi.fn()}
      testing={false}
      saving={false}
    />,
  )
}

describe('TelegramConfig fuel commands', () => {
  it('holds the switch while Telegram itself is off', () => {
    renderConfig({ telegram_enabled: 'false', telegram_inbound_enabled: 'false' })

    expect(screen.getByRole('checkbox', FUEL)).toBeDisabled()
  })

  it('gives the address to register with Telegram, on this host', () => {
    renderConfig({ telegram_enabled: 'true' })

    expect(
      screen.getByText(`${window.location.origin}/api/v1/webhooks/telegram`, { exact: false }),
    ).toHaveTextContent('secret_token=<WEBHOOK_TOKEN>')
  })
})
