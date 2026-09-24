import { useState } from 'react'
import type { ReactElement } from 'react'
import { useTranslation } from 'react-i18next'
import { formatDistanceToNow } from 'date-fns'

import { Mono, Toggle } from '@/components/ui'
import { useTimeFormat } from '@/hooks/useTimeFormat'
import { useUnitFormat } from '@/hooks/useUnitFormat'
import { livelinkService } from '@/services/livelinkService'
import type { DeviceReading } from '@/types/livelink'
import { getDateFnsLocale } from '@/utils/dateUtils'
import { getActionErrorMessage } from '@/utils/httpErrorHandler'
import { formatDateTime, parseAPITimestamp } from '@/utils/parseAPITimestamp'
import { formatSensorReading, sensorReadingName } from '@/utils/sensorReadings'
import { getParamDisplayName } from '@/utils/telemetryUnits'

/**
 * One MQTT device's readings: a name, a value, how old it is, and a switch
 * for whether the Live tab draws a gauge for it (spec G5; the operator's
 * "listed as toggles").
 *
 * The switch writes `show_on_dashboard` only. Storage never stops, so hiding
 * a reading and showing it again brings its whole history back.
 *
 * The value is device-attributed and may be old (GET /devices/{id}/readings
 * takes the newest stored row, subject to the storage interval), so the age
 * shown is the timestamp it actually has, never a promise of freshness.
 *
 * `compact` is the preset sensor's block: two readings to a row, names without
 * the sensor's own name in front, and one "last reading" line for the sensor
 * instead of an age on every row.
 */

interface Props {
  readings: DeviceReading[]
  /** Called after a switch is saved, so the drawer refetches. */
  onChanged: () => void
  compact?: boolean
  /** The sensor's name, dropped from the front of each reading's name in the
   *  compact list: under "Front tank", "Front tank level" reads "Level". */
  sensorLabel?: string
}

/** A value this much older than the sensor's newest is from a reading the
 *  gateway has stopped sending, so it is muted and marked. */
const STALE_MS = 30 * 60 * 1000

interface Row {
  reading: DeviceReading
  name: string
  shown: { text: string; unit: string } | null
  at: Date | null
  checked: boolean
}

export default function DeviceReadingsList({ readings, onChanged, compact, sensorLabel }: Props): ReactElement {
  const { t } = useTranslation('settings')
  const unitFormat = useUnitFormat()
  const [error, setError] = useState<string | null>(null)

  // Optimistic switch positions, keyed by param_key. Dropped whenever new
  // readings arrive, so after a refetch every switch shows what the SERVER
  // says rather than what was clicked earlier. React's "adjust state when a
  // prop changes" pattern, not an effect: it runs before the stale render.
  const [pending, setPending] = useState<Record<string, boolean>>({})
  const [seen, setSeen] = useState(readings)
  if (readings !== seen) {
    setSeen(readings)
    setPending({})
  }

  const toggle = async (paramKey: string, next: boolean): Promise<void> => {
    setError(null)
    setPending((current) => ({ ...current, [paramKey]: next }))
    try {
      await livelinkService.updateParameter(paramKey, { show_on_dashboard: next })
      onChanged()
    } catch (err) {
      setPending((current) => ({ ...current, [paramKey]: !next }))
      setError(getActionErrorMessage(err, t('integrations.readingSwitchAction')))
    }
  }

  const rows: Row[] = readings.map((reading) => ({
    reading,
    name: getParamDisplayName(reading.param_key, reading.display_name ?? null),
    // A preset sensor's reading says how it reads (Yes/No, "3 of 3"), the same
    // helper as the Live tab's tank card; anything else is a plain value.
    shown:
      reading.value == null
        ? null
        : formatSensorReading(reading.value, reading.param_key, reading.unit ?? null, reading, unitFormat, t),
    at: reading.timestamp ? parseAPITimestamp(reading.timestamp) : null,
    checked: pending[reading.param_key] ?? reading.show_on_dashboard,
  }))

  const errorLine = error ? (
    <p className="text-xs text-danger" role="alert">
      {error}
    </p>
  ) : null

  if (compact) {
    return (
      <CompactRows rows={rows} sensorLabel={sensorLabel} errorLine={errorLine} onToggle={toggle} />
    )
  }

  return (
    <section className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-text">{t('integrations.readingsHeading')}</h3>
        <p className="text-xs text-text-mute">{t('integrations.readingsSummary', { count: readings.length })}</p>
      </div>
      {errorLine}
      <ul className="divide-y divide-border rounded-control border border-border">
        {rows.map(({ reading, name, shown, at, checked }) => (
          <li key={reading.param_key} className="flex items-center gap-3 px-3 py-2">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm text-text">{name}</p>
              {at ? (
                <p className="text-xs text-text-mute">
                  {formatDistanceToNow(at, { addSuffix: true, locale: getDateFnsLocale() })}
                </p>
              ) : null}
            </div>
            <Value shown={shown} />
            <Toggle
              label={name}
              hideLabel
              checked={checked}
              onChange={(next) => void toggle(reading.param_key, next)}
            />
          </li>
        ))}
      </ul>
    </section>
  )
}

function Value({ shown, title, stale }: { shown: Row['shown']; title?: string; stale?: boolean }): ReactElement {
  const { t } = useTranslation('settings')
  if (!shown) return <span className="text-xs text-text-mute">{t('integrations.readingNone')}</span>
  return (
    <span title={title} className="shrink-0">
      <Mono size="sm" tabular tone={stale ? 'muted' : undefined}>
        {shown.text}
        {shown.unit ? <span className="ml-1 text-text-mute">{shown.unit}</span> : null}
      </Mono>
      {stale ? <span className="ml-1 text-xs text-text-mute">{t('integrations.readingOld')}</span> : null}
    </span>
  )
}

/** Its own component so only the compact list reads the time-format
 *  preference, which lives in the auth context. */
function CompactRows({
  rows,
  sensorLabel,
  errorLine,
  onToggle,
}: {
  rows: Row[]
  sensorLabel: string | undefined
  errorLine: ReactElement | null
  onToggle: (paramKey: string, next: boolean) => Promise<void>
}): ReactElement {
  const { t } = useTranslation('settings')
  const { timeFormat } = useTimeFormat()
  const times = rows.flatMap(({ at }) => (at ? [at.getTime()] : []))
  const newest = times.length > 0 ? Math.max(...times) : null

  return (
    <div className="space-y-1">
      {errorLine}
      <ul className="grid gap-x-6 sm:grid-cols-2">
        {rows.map(({ reading, name, shown, at, checked }) => (
          <li key={reading.param_key} className="flex items-center gap-2 border-b border-border py-1.5">
            <span className="min-w-0 flex-1 truncate text-sm text-text">{sensorReadingName(name, sensorLabel)}</span>
            <Value
              shown={shown}
              title={at ? formatDateTime(at, timeFormat) : undefined}
              stale={at !== null && newest !== null && newest - at.getTime() > STALE_MS}
            />
            {/* The full name: two tanks' "Level" switches must not read alike. */}
            <Toggle label={name} hideLabel checked={checked} onChange={(next) => void onToggle(reading.param_key, next)} />
          </li>
        ))}
      </ul>
      {newest !== null ? (
        <p className="text-xs text-text-mute">
          {t('integrations.lastReading', {
            age: formatDistanceToNow(newest, { addSuffix: true, locale: getDateFnsLocale() }),
          })}
        </p>
      ) : null}
    </div>
  )
}
