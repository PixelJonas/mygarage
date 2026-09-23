import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { IntegrationTab } from '@/types/livelink'

const svc = vi.hoisted(() => ({ getDevices: vi.fn(), listPresets: vi.fn() }))
vi.mock('@/services/livelinkService', () => ({ livelinkService: svc }))
vi.mock('@/services/vehicleService', () => ({
  vehicleService: { list: () => Promise.resolve({ vehicles: [], total: 0 }) },
}))
vi.mock('../SensorBlock', () => ({
  default: ({ device }: { device: { label: string } }) => <p>block {device.label}</p>,
}))
vi.mock('../SensorForm', () => ({
  default: ({ onCreated }: { onCreated: (d: unknown) => void }) => (
    <button onClick={() => onCreated({ device_id: 'mopeka-t3' })}>submit-sensor</button>
  ),
}))

import PresetDrawer from '../PresetDrawer'

const TAB = { id: 'preset:mopeka', label: 'Mopeka', kind: 'generic_mqtt' } as unknown as IntegrationTab
const PRESET = { name: 'mopeka', title: 'Mopeka', description: 'Mopeka Pro Check propane tank sensors.', kind: 'generic_mqtt', readings: [] }
const device = (id: string, label: string, preset_key: string | null) => ({ device_id: id, label, preset_key, kind: 'generic_mqtt' })

beforeEach(() => {
  vi.clearAllMocks()
  svc.listPresets.mockResolvedValue([PRESET])
  svc.getDevices.mockResolvedValue({
    total: 3,
    online_count: 0,
    devices: [
      device('mopeka-t1', 'Front tank', 'mopeka'),
      device('mopeka-t2', 'Rear tank', 'mopeka'),
      device('shed', 'Shed sensors', null),
    ],
  })
})

describe('PresetDrawer', () => {
  it('shows one block per sensor made from this preset, and no other device', async () => {
    render(<PresetDrawer open tab={TAB} onClose={vi.fn()} onChanged={vi.fn()} />)

    expect(await screen.findByText('block Front tank')).toBeInTheDocument()
    expect(screen.getByText('block Rear tank')).toBeInTheDocument()
    expect(screen.queryByText('block Shed sensors')).not.toBeInTheDocument()
    expect(screen.getByText(PRESET.description)).toBeInTheDocument()
  })

  it('adds a sensor from inside the drawer and refreshes the card', async () => {
    const onChanged = vi.fn()
    render(<PresetDrawer open tab={TAB} onClose={vi.fn()} onChanged={onChanged} />)

    fireEvent.click(await screen.findByRole('button', { name: 'integrations.addSensor' }))
    fireEvent.click(screen.getByRole('button', { name: 'submit-sensor' }))

    await waitFor(() => expect(onChanged).toHaveBeenCalled())
    expect(svc.getDevices).toHaveBeenCalledTimes(2)
  })

  it('says so when there are no sensors yet', async () => {
    svc.getDevices.mockResolvedValue({ total: 0, online_count: 0, devices: [] })
    render(<PresetDrawer open tab={TAB} onClose={vi.fn()} onChanged={vi.fn()} />)

    expect(await screen.findByText('integrations.noSensors')).toBeInTheDocument()
  })
})
