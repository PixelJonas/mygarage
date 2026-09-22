import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { render } from '../../../__tests__/test-utils'

// `livelinkService` is ONE object export, so it is mocked with a factory
// returning `{ livelinkService: { ... } }`, matching VehicleLiveLinkWidget's
// test. `import * as svc` plus vi.mocked() yields undefined and throws.
//
// EVERY loader the card calls on mount is stubbed, not just the ones a given
// test exercises: vi.mock with a factory leaves unlisted members undefined.
const listTopicMaps = vi.fn()
const createTopicMap = vi.fn()
const createDevice = vi.fn()
const discoverTopics = vi.fn()
const listPresets = vi.fn()
const deleteTopicMap = vi.fn()
const applyPreset = vi.fn()

vi.mock('@/services/livelinkService', () => ({
  livelinkService: {
    listTopicMaps: (...a: unknown[]) => listTopicMaps(...a),
    createTopicMap: (...a: unknown[]) => createTopicMap(...a),
    createDevice: (...a: unknown[]) => createDevice(...a),
    discoverTopics: (...a: unknown[]) => discoverTopics(...a),
    listPresets: (...a: unknown[]) => listPresets(...a),
    deleteTopicMap: (...a: unknown[]) => deleteTopicMap(...a),
    applyPreset: (...a: unknown[]) => applyPreset(...a),
  },
}))

import { MqttSourcesCard } from '../MqttSourcesCard'

const ROW = {
  id: 1,
  device_id: 'rvgw',
  topic: 'mygarage/rv/propane/tank1/level_percent',
  role: 'telemetry' as const,
  param_key: 'PROPANE_T1_LEVEL_PCT',
  value_path: null,
  unit: '%',
  param_class: 'propane',
  scale: '1',
  value_offset: '0',
  enabled: true,
}

beforeEach(() => {
  vi.clearAllMocks()
  listTopicMaps.mockResolvedValue([])
  listPresets.mockResolvedValue([])
  discoverTopics.mockResolvedValue([])
})

// `t` is mocked to return the KEY (src/__tests__/setup.ts), so every assertion
// below is on a translation key, never on English.
describe('MqttSourcesCard', () => {
  it('lists existing topic maps', async () => {
    listTopicMaps.mockResolvedValue([ROW])
    render(<MqttSourcesCard deviceId="rvgw" />)
    expect(await screen.findByText('PROPANE_T1_LEVEL_PCT')).toBeInTheDocument()
  })

  it('creates a generic device without a preset', async () => {
    createDevice.mockResolvedValue({ device_id: 'rvgw', kind: 'generic_mqtt' })
    render(<MqttSourcesCard deviceId={null} />)
    await userEvent.type(screen.getByLabelText('integrations.mqttDeviceId'), 'rvgw')
    await userEvent.click(
      screen.getByRole('button', { name: 'integrations.mqttCreateDevice' }),
    )
    await waitFor(() => {
      expect(createDevice).toHaveBeenCalledWith(
        expect.objectContaining({ device_id: 'rvgw', kind: 'generic_mqtt' }),
      )
    })
  })

  it('rejects a wildcard topic before calling the API', async () => {
    render(<MqttSourcesCard deviceId="rvgw" />)
    await userEvent.type(screen.getByLabelText('integrations.mqttMapTopic'), 'mygarage/rv/#')
    await userEvent.click(screen.getByRole('button', { name: 'integrations.mqttAddMapping' }))
    expect(
      await screen.findByText('integrations.mqttErrorsTopicMustBeExact'),
    ).toBeInTheDocument()
    expect(createTopicMap).not.toHaveBeenCalled()
  })

  it('warns that a discovered non-numeric topic cannot be mapped', async () => {
    discoverTopics.mockResolvedValue([
      { topic: 'mygarage/rv/gateway/ip', sample: '10.10.20.243' },
    ])
    render(<MqttSourcesCard deviceId="rvgw" />)
    await userEvent.click(screen.getByRole('button', { name: /integrations.mqttDiscover$/ }))
    expect(
      await screen.findByText('integrations.mqttErrorsSampleNotNumeric'),
    ).toBeInTheDocument()
  })

  it('prefills the param key from the topic tail, uppercased', async () => {
    render(<MqttSourcesCard deviceId="rvgw" />)
    await userEvent.type(
      screen.getByLabelText('integrations.mqttMapTopic'),
      'mygarage/rv/propane/tank1/level_percent',
    )
    await waitFor(() => {
      expect(screen.getByLabelText('integrations.mqttParamKey')).toHaveValue('LEVEL_PERCENT')
    })
  })
})
