import { describe, it, expect } from 'vitest'
import type { PresetReadingInfo } from '@/types/livelinkTopicMap'
import { discoveryFilter, suggestTopics } from '../suggestTopics'

const reading = (suffix: string, defaultTopic: string, keywords: string[], required = false): PresetReadingInfo => ({
  suffix,
  name: suffix.toLowerCase(),
  unit: null,
  default_topic: defaultTopic,
  keywords,
  required,
})

/** The Mopeka preset's readings, in its order. */
const READINGS = [
  reading('LEVEL_PCT', 'level_percent', ['level'], true),
  reading('TEMP_C', 'temperature_c', ['temp']),
  reading('SENSOR_BATT_PCT', 'battery_percent', ['batt']),
  reading('QUALITY', 'reading_quality', ['quality', 'signal']),
  reading('DEPTH_MM', 'depth_mm', ['depth', 'distance']),
  reading('REJECTED', 'rejected_readings', ['reject', 'ignored']),
  reading('AVAILABLE', 'availability', ['avail', 'heard']),
]

const LEVEL = 'mygarage/rv/propane/tank1/level_percent'

describe('suggestTopics', () => {
  it("finds every reading of the operator's own layout when the broker publishes them", () => {
    const heard = [
      LEVEL,
      'mygarage/rv/propane/tank1/temperature_c',
      'mygarage/rv/propane/tank1/battery_percent',
      'mygarage/rv/propane/tank1/reading_quality',
      'mygarage/rv/propane/tank1/depth_mm',
      'mygarage/rv/propane/tank1/rejected_readings',
      'mygarage/rv/propane/tank1/availability',
    ]

    expect(suggestTopics(LEVEL, READINGS, heard)).toEqual({
      TEMP_C: 'mygarage/rv/propane/tank1/temperature_c',
      SENSOR_BATT_PCT: 'mygarage/rv/propane/tank1/battery_percent',
      QUALITY: 'mygarage/rv/propane/tank1/reading_quality',
      DEPTH_MM: 'mygarage/rv/propane/tank1/depth_mm',
      REJECTED: 'mygarage/rv/propane/tank1/rejected_readings',
      AVAILABLE: 'mygarage/rv/propane/tank1/availability',
    })
  })

  it('matches a different layout by keyword, not by exact name', () => {
    // Somebody else's gateway: nested per-sensor topics with other names.
    const level = 'garage/mopeka_front/sensor/propane_level/state'
    const heard = [
      level,
      'garage/mopeka_front/sensor/tank_temperature/state',
      'garage/mopeka_front/sensor/battery_voltage_pct/state',
      'garage/mopeka_front/sensor/signal_strength/state',
    ]

    const suggested = suggestTopics(level, READINGS, heard)

    // The segment that varies is in the MIDDLE here (<node>/sensor/<name>/state),
    // so "siblings in the level topic's folder" would find nothing. The rule
    // varies whichever segment names the level, and keeps the rest fixed.
    expect(suggested.TEMP_C).toBe('garage/mopeka_front/sensor/tank_temperature/state')
    expect(suggested.SENSOR_BATT_PCT).toBe('garage/mopeka_front/sensor/battery_voltage_pct/state')
    expect(suggested.QUALITY).toBe('garage/mopeka_front/sensor/signal_strength/state')
    // Not heard, so not guessed: no mapping that would never report.
    expect(suggested.DEPTH_MM).toBeUndefined()
    expect(suggested.REJECTED).toBeUndefined()
  })

  it('falls back to the reference names when nothing is heard', () => {
    expect(suggestTopics(LEVEL, READINGS, [])).toEqual({
      TEMP_C: 'mygarage/rv/propane/tank1/temperature_c',
      SENSOR_BATT_PCT: 'mygarage/rv/propane/tank1/battery_percent',
      QUALITY: 'mygarage/rv/propane/tank1/reading_quality',
      DEPTH_MM: 'mygarage/rv/propane/tank1/depth_mm',
      REJECTED: 'mygarage/rv/propane/tank1/rejected_readings',
      AVAILABLE: 'mygarage/rv/propane/tank1/availability',
    })
  })

  it('never offers one topic for two readings', () => {
    // 'temperature_signal' contains both 'temp' and 'signal'.
    const heard = [LEVEL, 'mygarage/rv/propane/tank1/temperature_signal']

    const suggested = suggestTopics(LEVEL, READINGS, heard)

    expect(suggested.TEMP_C).toBe('mygarage/rv/propane/tank1/temperature_signal')
    expect(suggested.QUALITY).toBeUndefined()
  })

  it("never offers another tank's topic", () => {
    // Only topics in the level topic's own shape count, so tank 2's
    // temperature is ignored. Tank 1's level WAS heard, so the broker was
    // listening and tank 1 publishes no temperature: no guess either.
    const heard = [LEVEL, 'mygarage/rv/propane/tank2/temperature_c']

    expect(suggestTopics(LEVEL, READINGS, heard).TEMP_C).toBeUndefined()
  })

  it("guesses when only another tank's topics were heard", () => {
    // Nothing in tank 1's shape, not even its level: nothing retained there.
    const heard = ['mygarage/rv/propane/tank2/level_percent', 'mygarage/rv/propane/tank2/temperature_c']

    expect(suggestTopics(LEVEL, READINGS, heard).TEMP_C).toBe('mygarage/rv/propane/tank1/temperature_c')
  })

  it('varies the LAST segment that names the level', () => {
    const level = 'levels/rv/tank1/level_percent'
    const heard = [level, 'levels/rv/tank1/temperature_c']

    expect(suggestTopics(level, READINGS, heard).TEMP_C).toBe('levels/rv/tank1/temperature_c')
  })

  it('suggests nothing when the level alone was heard', () => {
    // The broker answered and publishes nothing else there, so a guess would
    // be a mapping that never reports. Nor is the level offered for another
    // reading.
    expect(suggestTopics(LEVEL, READINGS, [LEVEL])).toEqual({})
  })

  it('guesses in the same shape when nothing is heard for a mid-topic layout', () => {
    const level = 'garage/mopeka_front/sensor/propane_level/state'

    expect(suggestTopics(level, READINGS, []).TEMP_C).toBe('garage/mopeka_front/sensor/temperature_c/state')
  })

  it('suggests nothing without a level topic to start from', () => {
    expect(suggestTopics('', READINGS, [])).toEqual({})
    expect(suggestTopics('level_percent', READINGS, [])).toEqual({})
  })
})

describe('discoveryFilter', () => {
  it("listens on the reference layout's own folder", () => {
    expect(discoveryFilter(LEVEL, READINGS)).toBe('mygarage/rv/propane/tank1/#')
  })

  it('listens above the varying segment for a mid-topic layout', () => {
    expect(discoveryFilter('garage/mopeka_front/sensor/propane_level/state', READINGS)).toBe(
      'garage/mopeka_front/sensor/#',
    )
  })

  it('has nothing to listen on without a shape', () => {
    expect(discoveryFilter('level_percent', READINGS)).toBeNull()
  })
})

