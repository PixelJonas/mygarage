import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const getSettings = vi.fn()
const updateSettings = vi.fn()
vi.mock('@/services/livelinkService', () => ({
  livelinkService: {
    getSettings: () => getSettings(),
    updateSettings: (u: unknown) => updateSettings(u),
  },
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import GeneralSettingsDrawer from '../GeneralSettingsDrawer'

const SETTINGS = {
  enabled: true,
  has_global_token: true,
  ingestion_url: 'http://x/api/v1/livelink/ingest',
  telemetry_retention_days: 90,
  session_timeout_minutes: 5,
  device_offline_timeout_minutes: 15,
  daily_aggregation_enabled: true,
  firmware_check_enabled: true,
  alert_cooldown_minutes: 30,
  session_grace_period_seconds: 60,
  session_gap_minutes: 15,
  session_boundary_mode: 'movement',
  notify_device_offline: true,
  notify_threshold_alerts: true,
  notify_firmware_update: true,
  notify_new_device: true,
}

/** Field renders the unit inside the label, so it is part of the name. */
const OFFLINE = 'modal.livelink.deviceOfflineTimeout (modal.livelink.minutes)'

const renderDrawer = () => {
  const onChanged = vi.fn()
  render(<GeneralSettingsDrawer open onClose={vi.fn()} onChanged={onChanged} />)
  return { onChanged }
}

beforeEach(() => {
  vi.clearAllMocks()
  getSettings.mockResolvedValue(SETTINGS)
  updateSettings.mockImplementation((u: object) => Promise.resolve({ ...SETTINGS, ...u }))
})

describe('GeneralSettingsDrawer', () => {
  it('saves a number on Save, not on every keystroke, and sends only what changed', async () => {
    // The modal PUT on every keystroke: typing 20 sent 2, then 20.
    renderDrawer()
    const field = await screen.findByLabelText(OFFLINE)

    fireEvent.change(field, { target: { value: '2' } })
    fireEvent.change(field, { target: { value: '20' } })
    expect(updateSettings).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'modal.livelink.save' }))

    await waitFor(() => expect(updateSettings).toHaveBeenCalledTimes(1))
    expect(updateSettings).toHaveBeenCalledWith({ device_offline_timeout_minutes: 20 })
  })

  it.each(['4', '20.5', '20junk', ''])('refuses %j and sends nothing', async (typed) => {
    // parseInt reads 20.5 and 20junk as 20, which would save a value the
    // operator never typed.
    renderDrawer()
    const field = await screen.findByLabelText(OFFLINE)

    fireEvent.change(field, { target: { value: typed } })
    fireEvent.click(screen.getByRole('button', { name: 'modal.livelink.save' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('settings:integrations.numberOutOfRange')
    expect(updateSettings).not.toHaveBeenCalled()
  })

  it('switching LiveLink off saves at once and refreshes the card', async () => {
    // Every tab's status follows the master switch.
    const { onChanged } = renderDrawer()

    fireEvent.click(await screen.findByLabelText('modal.enableLiveLink'))

    await waitFor(() => expect(updateSettings).toHaveBeenCalledWith({ enabled: false }))
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
  })

  it('says so when the settings cannot load, and can retry', async () => {
    getSettings.mockRejectedValueOnce(new Error('down'))
    renderDrawer()

    expect(await screen.findByText('settings:integrations.settingsLoadError')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'common:retry' }))

    expect(await screen.findByLabelText(OFFLINE)).toBeInTheDocument()
  })
})
