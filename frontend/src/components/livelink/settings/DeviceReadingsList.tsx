import { useState } from 'react'
import type { ReactElement } from 'react'
import { useTranslation } from 'react-i18next'
import { formatDistanceToNow } from 'date-fns'

import { Mono, Toggle } from '@/components/ui'
import { useUnitFormat } from '@/hooks/useUnitFormat'
import { livelinkService } from '@/services/livelinkService'
import type { DeviceReading } from '@/types/livelink'
import { getDateFnsLocale } from '@/utils/dateUtils'
import { getActionErrorMessage } from '@/utils/httpErrorHandler'
import { parseAPITimestamp } from '@/utils/parseAPITimestamp'
import { convertTelemetryValue, getParamDisplayName } from '@/utils/telemetryUnits'

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
 */

interface Props {
  readings: DeviceReading[]
  /** Called after a switch is saved, so the drawer refetches. */
  onChanged: () => void
}

export default function DeviceReadingsList({ readings, onChanged }: Props): ReactElement {
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

  return (
    <section className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-text">{t('integrations.readingsHeading')}</h3>
        <p className="text-xs text-text-mute">{t('integrations.readingsSummary', { count: readings.length })}</p>
      </div>
      {error ? (
        <p className="text-xs text-danger" role="alert">
          {error}
        </p>
      ) : null}
      <ul className="divide-y divide-border rounded-control border border-border">
        {readings.map((reading) => {
          const name = getParamDisplayName(reading.param_key, reading.display_name ?? null)
          const shown =
            reading.value == null
              ? null
              : convertTelemetryValue(reading.value, reading.param_key, reading.unit ?? null, unitFormat)
          const at = reading.timestamp ? parseAPITimestamp(reading.timestamp) : null
          const checked = pending[reading.param_key] ?? reading.show_on_dashboard
          return (
            <li key={reading.param_key} className="flex items-center gap-3 px-3 py-2">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm text-text">{name}</p>
                {at ? (
                  <p className="text-xs text-text-mute">
                    {formatDistanceToNow(at, { addSuffix: true, locale: getDateFnsLocale() })}
                  </p>
                ) : null}
              </div>
              {shown ? (
                <Mono size="sm" tabular>
                  {shown.text}
                  {shown.unit ? <span className="ml-1 text-text-mute">{shown.unit}</span> : null}
                </Mono>
              ) : (
                <span className="text-xs text-text-mute">{t('integrations.readingNone')}</span>
              )}
              <Toggle
                label={name}
                hideLabel
                checked={checked}
                onChange={(next) => void toggle(reading.param_key, next)}
              />
            </li>
          )
        })}
      </ul>
    </section>
  )
}
