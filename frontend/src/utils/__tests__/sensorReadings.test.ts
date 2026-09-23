import { describe, it, expect } from 'vitest'
import { formatSensorReading, sensorReadingName, tankLevelTone } from '../sensorReadings'
import { makeUnitFormat } from '../unitFormat'
import { presetUnitsFor } from '@/types/units'

const IMPERIAL = makeUnitFormat(presetUnitsFor('imperial', 'us'))
/** Echoes the key and its options, so an assertion can see both. */
const t = (key: string, options?: Record<string, unknown>): string =>
  options ? `${key}${JSON.stringify(options)}` : key

describe('sensorReadingName', () => {
  it("drops the sensor's name from the front", () => {
    expect(sensorReadingName('Tank 1 sensor heard', 'Tank 1')).toBe('Sensor heard')
  })

  it('shows a name set by hand whole', () => {
    expect(sensorReadingName('Bottle temp', 'Tank 1')).toBe('Bottle temp')
  })

  it('does not cut a name that only starts with the same letters', () => {
    // "Tank 10 level" is not a reading of "Tank 1".
    expect(sensorReadingName('Tank 10 level', 'Tank 1')).toBe('Tank 10 level')
  })

  it('leaves the name alone without a sensor', () => {
    expect(sensorReadingName('level', undefined)).toBe('Level')
  })
})

describe('formatSensorReading', () => {
  it('reads a boolean as Yes or No, never 1.0', () => {
    expect(formatSensorReading(1, 'K', null, { format: 'boolean' }, IMPERIAL, t)).toStrictEqual({
      text: 'common:yes',
      unit: '',
    })
    expect(formatSensorReading(0, 'K', null, { format: 'boolean' }, IMPERIAL, t).text).toBe('common:no')
  })

  it('reads a count as a whole number', () => {
    expect(formatSensorReading(2.0, 'K', null, { format: 'count' }, IMPERIAL, t)).toStrictEqual({
      text: '2',
      unit: '',
    })
  })

  it('reads a grade against its top', () => {
    expect(
      formatSensorReading(3, 'K', null, { format: 'of_max', max_value: 3 }, IMPERIAL, t).text,
    ).toBe('common:ofMax{"value":"3","max":3}')
  })

  it('sends a plain value through the unit adapter', () => {
    // 35 C x 9/5 + 32 = 95.0 F.
    expect(formatSensorReading(35, 'PROPANE_T1_TEMP_C', 'C', { format: 'value' }, IMPERIAL, t)).toStrictEqual({
      text: '95.0',
      unit: '°F',
    })
  })

  it('treats a grade with no top as a plain value', () => {
    expect(formatSensorReading(3, 'K', null, { format: 'of_max', max_value: null }, IMPERIAL, t).text).toBe('3.0')
  })
})

describe('tankLevelTone', () => {
  it.each([
    [100, 'success'],
    [25, 'success'],
    [24.9, 'warning'],
    [10, 'warning'],
    [9.9, 'danger'],
    [0, 'danger'],
  ])('%s%% is %s', (level, tone) => {
    expect(tankLevelTone(level)).toBe(tone)
  })
})
