import { useId } from 'react'
import type { ReactElement } from 'react'
import { useTranslation } from 'react-i18next'
import { formatDistanceToNow } from 'date-fns'

import { Mono } from '@/components/ui'
import type { LiveSensor, TelemetryLatestValue } from '@/types/livelink'
import { getDateFnsLocale } from '@/utils/dateUtils'
import { parseAPITimestamp } from '@/utils/parseAPITimestamp'
import {
  formatSensorReading,
  readingTone,
  sensorReadingName,
  tankContent,
  tankLevelTone,
} from '@/utils/sensorReadings'
import { getParamDisplayName } from '@/utils/telemetryUnits'
import type { UnitFormat } from '@/utils/unitFormat'
import TankGraphic from './TankGraphic'

/**
 * One propane tank on the Live tab: the tank filled to its level, and the
 * sensor's other readings beside it under short names ("Sensor heard", not
 * "Tank 1 sensor heard": the card already says which tank).
 *
 * The show-on-dashboard switches from Settings still apply. A hidden reading
 * leaves the list; a hidden level takes the tank graphic with it. The colours
 * follow the tank's own alert lines, also set in Settings.
 */

interface Props {
  sensor: LiveSensor
  /** The vehicle's latest values, by param_key. */
  values: ReadonlyMap<string, TelemetryLatestValue>
  unitFormat: UnitFormat
}

export default function TankCard({ sensor, values, unitFormat }: Props): ReactElement {
  const { t } = useTranslation('vehicles')
  const headingId = useId()
  const fill = sensor.fill_key ? values.get(sensor.fill_key) : undefined
  const { drawsTank, rows } = tankContent(sensor, values)

  const times = (sensor.readings ?? []).flatMap((reading) => {
    const at = values.get(reading.param_key)?.timestamp
    const date = at ? parseAPITimestamp(at) : null
    return date ? [date.getTime()] : []
  })
  const newest = times.length > 0 ? Math.max(...times) : null

  return (
    <section
      aria-labelledby={headingId}
      className={`rounded-card border border-border bg-surface p-4 ${sensor.online ? '' : 'opacity-70'}`}
    >
      <header className="mb-3 flex items-center justify-between gap-3">
        <h3 id={headingId} className="truncate text-base font-semibold text-text">
          {sensor.label}
        </h3>
        <span className="flex shrink-0 items-center gap-1.5 text-xs text-text-mute">
          <span
            aria-hidden="true"
            className={`h-2 w-2 rounded-full ${sensor.online ? 'bg-success' : 'bg-danger'}`}
          />
          {sensor.online ? t('livelink.statusConnected') : t('livelink.statusDeviceOffline')}
        </span>
      </header>

      <div className="flex items-center gap-5">
        {drawsTank ? (
          <TankGraphic
            level={fill?.value ?? null}
            tone={tankLevelTone(fill?.alert_band)}
            label={
              fill ? t('livelink.tankLevel', { level: Math.round(fill.value) }) : t('livelink.tankLevelUnknown')
            }
            className="h-40 w-24 shrink-0"
          />
        ) : null}

        {rows.length > 0 ? (
          <dl className="grid flex-1 grid-cols-[1fr_auto] items-baseline gap-x-4 gap-y-2 text-sm">
            {rows.map(({ reading, value }) => {
              const shown = formatSensorReading(
                value.value,
                value.param_key,
                value.unit ?? null,
                reading,
                unitFormat,
                t,
              )
              const name = getParamDisplayName(value.param_key, value.display_name ?? null)
              return (
                <div key={reading.param_key} className="contents">
                  <dt className="truncate text-text-mute">{sensorReadingName(name, sensor.label)}</dt>
                  <dd className="text-right">
                    <Mono size="sm" tabular tone={readingTone(value.alert_band)}>
                      {shown.text}
                      {shown.unit ? <span className="ml-1 text-text-mute">{shown.unit}</span> : null}
                    </Mono>
                  </dd>
                </div>
              )
            })}
          </dl>
        ) : null}
      </div>

      {newest !== null ? (
        <p className="mt-3 text-xs text-text-mute">
          {t('livelink.lastReading', {
            age: formatDistanceToNow(newest, { addSuffix: true, locale: getDateFnsLocale() }),
          })}
        </p>
      ) : null}
    </section>
  )
}
