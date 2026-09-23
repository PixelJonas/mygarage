/**
 * Showing a preset sensor's readings: the Live tab's tank card and the
 * settings drawer's compact list share these, so a reading reads the same in
 * both places.
 */

import type { LiveSensor, TelemetryLatestValue } from '@/types/livelink'
import type { ConvertedTelemetry } from './telemetryUnits'
import { convertTelemetryValue } from './telemetryUnits'
import { formatAtPrecision, type UnitFormat } from './unitFormat'

/** How the server says a reading is shown (the preset declares it). */
export type ReadingFormat = 'value' | 'boolean' | 'count' | 'of_max'

export interface ReadingShownAs {
  format?: ReadingFormat
  max_value?: number | null
}

type Translate = (key: string, options?: Record<string, unknown>) => string

/** The Live tab's fill turns amber below this, then red below the next. */
const LOW_LEVEL = 25
const EMPTY_LEVEL = 10

/**
 * "Tank 1 sensor heard" under "Tank 1" is "Sensor heard". A name someone
 * changed by hand, which no longer starts with the sensor's name, is shown
 * whole.
 */
export function sensorReadingName(name: string, sensorLabel: string | null | undefined): string {
  const prefix = sensorLabel ? `${sensorLabel} ` : ''
  const rest = prefix && name.startsWith(prefix) ? name.slice(prefix.length) : name
  return rest.charAt(0).toUpperCase() + rest.slice(1)
}

/**
 * One reading as the user reads it.
 *
 * `value` readings go through the unit adapter like every other gauge; the
 * rest are not quantities: a boolean is Yes or No, a count a whole number, a
 * grade "3 of 3".
 */
export function formatSensorReading(
  value: number,
  paramKey: string,
  unit: string | null,
  shownAs: ReadingShownAs,
  unitFormat: UnitFormat,
  t: Translate,
): ConvertedTelemetry {
  switch (shownAs.format) {
    case 'boolean':
      return { text: value >= 0.5 ? t('common:yes') : t('common:no'), unit: '' }
    case 'count':
      return { text: formatAtPrecision(Math.round(value), 0), unit: '' }
    case 'of_max':
      if (shownAs.max_value != null) {
        return {
          text: t('common:ofMax', { value: formatAtPrecision(Math.round(value), 0), max: shownAs.max_value }),
          unit: '',
        }
      }
      break
    default:
      break
  }
  return convertTelemetryValue(value, paramKey, unit, unitFormat)
}

/** The tank's fill colour for a level in percent. */
export function tankLevelTone(level: number): 'success' | 'warning' | 'danger' {
  if (level < EMPTY_LEVEL) return 'danger'
  if (level < LOW_LEVEL) return 'warning'
  return 'success'
}

/** What one tank card shows. */
export interface TankContent {
  /** The level is mapped and not hidden (reported or not), so the tank is drawn. */
  readonly drawsTank: boolean
  /** The readings beside it: reported, not hidden, not the level. */
  readonly rows: ReadonlyArray<{ reading: NonNullable<LiveSensor['readings']>[number]; value: TelemetryLatestValue }>
}

/**
 * Apply the Settings switches to one sensor's card. A hidden reading leaves
 * the list; a hidden level takes the tank graphic with it. A card left with
 * neither is not drawn at all.
 */
export function tankContent(
  sensor: LiveSensor,
  values: ReadonlyMap<string, TelemetryLatestValue>,
): TankContent {
  const shown = (value: TelemetryLatestValue | undefined): boolean => value?.show_on_dashboard !== false
  return {
    drawsTank: sensor.fill_key != null && shown(values.get(sensor.fill_key)),
    rows: (sensor.readings ?? []).flatMap((reading) => {
      const value = values.get(reading.param_key)
      return reading.param_key !== sensor.fill_key && value && shown(value) ? [{ reading, value }] : []
    }),
  }
}
