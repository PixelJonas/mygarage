/**
 * One tank's card, through the REAL unit layer: the temperature it shows is
 * unit behaviour, and a stubbed converter would let a Celsius value reach a
 * Fahrenheit account unconverted.
 */
import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'

import type { LiveSensor, TelemetryLatestValue } from '@/types/livelink'
import { presetUnitsFor } from '@/types/units'
import { makeUnitFormat } from '@/utils/unitFormat'
import TankCard from '../TankCard'

const IMPERIAL = makeUnitFormat(presetUnitsFor('imperial', 'us'))
const K = (suffix: string): string => `PROPANE_T1_${suffix}`

const SENSOR: LiveSensor = {
  device_id: 'mopeka-t1',
  label: 'Tank 1',
  preset_key: 'mopeka',
  online: true,
  last_seen: '2026-09-22T12:00:00Z',
  fill_key: K('LEVEL_PCT'),
  readings: [
    { param_key: K('LEVEL_PCT'), format: 'value', max_value: null },
    { param_key: K('TEMP_C'), format: 'value', max_value: null },
    { param_key: K('QUALITY'), format: 'of_max', max_value: 3 },
    { param_key: K('AVAILABLE'), format: 'boolean', max_value: null },
  ],
}

const value = (suffix: string, name: string, v: number, over: Partial<TelemetryLatestValue> = {}) => ({
  param_key: K(suffix),
  value: v,
  unit: null,
  display_name: `Tank 1 ${name}`,
  timestamp: '2026-09-22T12:00:00Z',
  in_warning: false,
  show_on_dashboard: true,
  ...over,
})

const VALUES = [
  value('LEVEL_PCT', 'level', 72, { unit: '%' }),
  value('TEMP_C', 'temperature', 35, { unit: 'C' }),
  value('QUALITY', 'reading quality', 3),
  value('AVAILABLE', 'sensor heard', 1),
] satisfies TelemetryLatestValue[]

const renderCard = (values: TelemetryLatestValue[] = VALUES, sensor: LiveSensor = SENSOR) =>
  render(
    <TankCard sensor={sensor} values={new Map(values.map((v) => [v.param_key, v]))} unitFormat={IMPERIAL} />,
  )

/** The value shown beside a reading's short name. */
const shownFor = (name: string): string | null =>
  screen.getByText(name, { selector: 'dt' }).nextElementSibling?.textContent ?? null

describe('TankCard', () => {
  it('names the tank and draws it at its level', () => {
    renderCard()

    expect(screen.getByRole('heading', { name: 'Tank 1' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'livelink.tankLevel' })).toBeInTheDocument()
    expect(screen.getByText('72%')).toBeInTheDocument()
  })

  it('lists the other readings under short names, the level not among them', () => {
    renderCard()

    const names = screen.getAllByRole('term').map((el) => el.textContent)
    expect(names).toEqual(['Temperature', 'Reading quality', 'Sensor heard'])
  })

  it('shows each value the way its reading says', () => {
    renderCard()

    // 35 C is 95.0 F through the adapter; heard is Yes, not 1.0; quality is a grade.
    expect(shownFor('Temperature')).toBe('95.0°F')
    expect(shownFor('Sensor heard')).toBe('common:yes')
    expect(shownFor('Reading quality')).toBe('common:ofMax')
  })

  it('drops a hidden reading, and a hidden level takes the tank with it', () => {
    renderCard([
      value('LEVEL_PCT', 'level', 72, { unit: '%', show_on_dashboard: false }),
      value('TEMP_C', 'temperature', 35, { unit: 'C', show_on_dashboard: false }),
      value('AVAILABLE', 'sensor heard', 1),
    ])

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.queryByText('Temperature')).not.toBeInTheDocument()
    expect(screen.getByText('Sensor heard')).toBeInTheDocument()
  })

  it('draws an empty tank until the level first reports', () => {
    renderCard(VALUES.filter((v) => v.param_key !== K('LEVEL_PCT')))

    expect(screen.getByRole('img', { name: 'livelink.tankLevelUnknown' })).toBeInTheDocument()
  })

  it('says whether the tank is reporting', () => {
    renderCard(VALUES, { ...SENSOR, online: false })

    const header = screen.getByRole('heading', { name: 'Tank 1' }).parentElement!
    expect(within(header).getByText('livelink.statusDeviceOffline')).toBeInTheDocument()
  })

  it('says how old the tank is once, not on every row', () => {
    renderCard()

    expect(screen.getAllByText('livelink.lastReading')).toHaveLength(1)
  })
})
