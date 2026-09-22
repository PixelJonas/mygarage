import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '../../../__tests__/test-utils'
import { fireEvent } from '@testing-library/react'

const listPresets = vi.fn()
const applyPreset = vi.fn()
const createDevice = vi.fn()
vi.mock('@/services/livelinkService', () => ({
  livelinkService: {
    listPresets: () => listPresets(),
    applyPreset: (name: string, deviceId: string, vin?: string | null) =>
      applyPreset(name, deviceId, vin),
    createDevice: (body: unknown) => createDevice(body),
  },
}))
const listVehicles = vi.fn()
vi.mock('@/services/vehicleService', () => ({
  default: { list: () => listVehicles() },
}))

import AddSourceDrawer from '../AddSourceDrawer'

const VEHICLE = { vin: '1HGBH41JXMN109186', nickname: 'Durango', year: 2023, make: 'KZ', model: 'RV' }
const PRESET = {
  name: 'mopeka_two_tank',
  title: 'Mopeka',
  description: 'Two sensors.',
  kind: 'generic_mqtt',
  row_count: 17,
}

/** What axios rejects with, as far as getActionErrorMessage reads it. */
const httpError = (status: number, detail: string): Error =>
  Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    response: { status, data: { detail } },
  })

const renderDrawer = (props: Partial<Parameters<typeof AddSourceDrawer>[0]> = {}) => {
  const onClose = vi.fn()
  const onCreated = vi.fn()
  const utils = render(<AddSourceDrawer open onClose={onClose} onCreated={onCreated} {...props} />)
  return { ...utils, onClose, onCreated }
}

const typeDeviceId = (value: string): void => {
  fireEvent.change(screen.getByLabelText('integrations.mqttDeviceId'), { target: { value } })
}

beforeEach(() => {
  vi.clearAllMocks()
  listPresets.mockResolvedValue([PRESET])
  listVehicles.mockResolvedValue({ vehicles: [VEHICLE], total: 1 })
  applyPreset.mockResolvedValue({ device_id: 'rvgw' })
  createDevice.mockResolvedValue({ device_id: 'hand1' })
})

describe('AddSourceDrawer', () => {
  it('lists the preset catalog', async () => {
    renderDrawer()

    expect(await screen.findByText('Mopeka')).toBeInTheDocument()
    expect(screen.getByText('Two sensors.')).toBeInTheDocument()
  })

  it('applies a preset with the chosen vehicle, then notifies and closes', async () => {
    // An unlinked generic_mqtt device drops every message: generic_mqtt is
    // requires_link=True and ingest returns before storage. So the vehicle has
    // to be selectable at creation.
    const { onCreated, onClose } = renderDrawer()
    await screen.findByText('Mopeka')
    await screen.findByRole('option', { name: 'Durango' })

    typeDeviceId('rvgw')
    fireEvent.change(screen.getByLabelText('integrations.sourceVehicle'), {
      target: { value: VEHICLE.vin },
    })
    fireEvent.click(screen.getByRole('button', { name: 'integrations.mqttApplyPreset' }))

    await waitFor(() =>
      expect(applyPreset).toHaveBeenCalledWith('mopeka_two_tank', 'rvgw', VEHICLE.vin),
    )
    // Without onCreated the operator applies a preset and no tab appears until
    // they reload the page.
    await waitFor(() => expect(onCreated).toHaveBeenCalled())
    expect(onClose).toHaveBeenCalled()
  })

  it('sends no vehicle, not an empty string, when left unlinked', async () => {
    renderDrawer()
    await screen.findByText('Mopeka')

    typeDeviceId('rvgw')
    fireEvent.click(screen.getByRole('button', { name: 'integrations.mqttApplyPreset' }))

    await waitFor(() => expect(applyPreset).toHaveBeenCalledWith('mopeka_two_tank', 'rvgw', null))
  })

  it('creates a blank device with its label and vehicle, then notifies', async () => {
    const { onCreated } = renderDrawer()
    await screen.findByText('Mopeka')
    await screen.findByRole('option', { name: 'Durango' })

    typeDeviceId('hand1')
    fireEvent.change(screen.getByLabelText('integrations.sourceVehicle'), {
      target: { value: VEHICLE.vin },
    })
    fireEvent.change(screen.getByLabelText('integrations.mqttDeviceLabel'), {
      target: { value: 'Shed sensors' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'integrations.mqttCreateDevice' }))

    await waitFor(() =>
      expect(createDevice).toHaveBeenCalledWith({
        device_id: 'hand1',
        kind: 'generic_mqtt',
        label: 'Shed sensors',
        vin: VEHICLE.vin,
      }),
    )
    await waitFor(() => expect(onCreated).toHaveBeenCalled())
  })

  it('holds both actions until a device id is entered', async () => {
    renderDrawer()
    await screen.findByText('Mopeka')

    expect(screen.getByRole('button', { name: 'integrations.mqttApplyPreset' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'integrations.mqttCreateDevice' })).toBeDisabled()
  })

  it('rejects an id that cannot be a URL path segment, before sending it', async () => {
    // The backend enforces the same pattern. Catching it here names the rule
    // at the field instead of after a round trip.
    renderDrawer()
    await screen.findByText('Mopeka')

    typeDeviceId('rv/gw')

    expect(await screen.findByRole('alert')).toHaveTextContent('integrations.deviceIdBadChar')
    expect(screen.getByRole('button', { name: 'integrations.mqttApplyPreset' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'integrations.mqttCreateDevice' })).toBeDisabled()
    expect(applyPreset).not.toHaveBeenCalled()
  })

  it('says what is wrong rather than repeating the rule', async () => {
    // The hint above the field already states the rule. The error names the
    // actual problem: a bad first character, or the first character that
    // is not allowed.
    renderDrawer()
    await screen.findByText('Mopeka')

    typeDeviceId('-gw')
    expect(await screen.findByRole('alert')).toHaveTextContent('integrations.deviceIdStart')

    typeDeviceId('gw#1')
    expect(await screen.findByRole('alert')).toHaveTextContent('integrations.deviceIdBadChar')
  })

  it('accepts the id shapes the backend accepts', async () => {
    renderDrawer()
    await screen.findByText('Mopeka')

    typeDeviceId('rv-gateway.2_b')

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'integrations.mqttApplyPreset' })).toBeEnabled()
  })

  it("shows the server's reason and stays open when creation fails", async () => {
    applyPreset.mockRejectedValue(httpError(409, 'Device rvgw already exists'))
    const { onCreated, onClose } = renderDrawer()
    await screen.findByText('Mopeka')

    typeDeviceId('rvgw')
    fireEvent.click(screen.getByRole('button', { name: 'integrations.mqttApplyPreset' }))

    expect(await screen.findByText(/Device rvgw already exists/)).toBeInTheDocument()
    expect(onCreated).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('starts empty when reopened after a success', async () => {
    const { rerender } = renderDrawer()
    await screen.findByText('Mopeka')
    typeDeviceId('rvgw')
    fireEvent.click(screen.getByRole('button', { name: 'integrations.mqttApplyPreset' }))
    await waitFor(() => expect(applyPreset).toHaveBeenCalled())

    rerender(<AddSourceDrawer open={false} onClose={() => {}} onCreated={() => {}} />)
    rerender(<AddSourceDrawer open onClose={() => {}} onCreated={() => {}} />)

    expect(await screen.findByLabelText('integrations.mqttDeviceId')).toHaveValue('')
  })
})
