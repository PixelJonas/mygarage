import { useTranslation } from 'react-i18next'

import { useNearestOdometer } from '../../hooks/queries/useOdometerRecords'
import { useUnitFormat } from '../../hooks/useUnitFormat'
import { formatDateForDisplay } from '../../utils/dateUtils'
import { Button, Field, Input } from '../ui'

interface MountEventFieldsProps {
  vin: string
  /** Prefix for the two input ids and the suggestion's test id. */
  idPrefix: string
  dateLabel: string
  /** YYYY-MM-DD. The caller defaults it to today with `formatDateForInput()`. */
  date: string
  onDateChange: (next: string) => void
  odometerLabel: string
  odometerHint?: string
  /** The odometer as typed, in the user's distance unit. */
  odometer: string
  onOdometerChange: (next: string) => void
}

/**
 * A date and an odometer, with the vehicle's nearest reading offered beneath.
 *
 * Used by every dialog that records where a tire went and when: Add Tire on
 * a corner, Mount, Dismount, Retire, Rotate, Set fit, and both halves of the
 * period editor. Before v3.4.0 each of those had a bare odometer input and no
 * date at all, so every operation was recorded as today.
 *
 * The suggestion is offered, never applied. It shows the reading's own date
 * and how far off it is, because the nearest reading to an installation can
 * sit on the far side of it, and only the user can judge that. Use fills the
 * field in display units through the same adapter the field reads in.
 */
export default function MountEventFields({
  vin,
  idPrefix,
  dateLabel,
  date,
  onDateChange,
  odometerLabel,
  odometerHint,
  odometer,
  onOdometerChange,
}: MountEventFieldsProps) {
  const { t } = useTranslation('vehicles')
  const u = useUnitFormat()
  const nearest = useNearestOdometer(vin, date)
  const reading = nearest.isSuccess ? (nearest.data ?? null) : undefined

  const offset = (daysAway: number): string => {
    if (daysAway === 0) return t('tireList.suggestionSameDay')
    if (daysAway < 0) return t('tireList.suggestionEarlier', { count: -daysAway })
    return t('tireList.suggestionLater', { count: daysAway })
  }

  return (
    <div className="space-y-3">
      <Field id={`${idPrefix}-date`} label={dateLabel}>
        <Input
          id={`${idPrefix}-date`}
          type="date"
          value={date}
          onChange={(e) => onDateChange(e.target.value)}
        />
      </Field>
      <Field id={`${idPrefix}-odometer`} label={odometerLabel} hint={odometerHint}>
        <Input
          id={`${idPrefix}-odometer`}
          type="number"
          step={u.distance.step}
          value={odometer}
          onChange={(e) => onOdometerChange(e.target.value)}
        />
      </Field>
      {reading ? (
        <div
          data-testid={`${idPrefix}-suggestion`}
          className="flex flex-wrap items-center gap-2 text-sm text-text-mute"
        >
          <span>
            {t('tireList.suggestion', {
              odometer: u.distance.format(Number(reading.odometer_km)),
              date: formatDateForDisplay(reading.date),
              offset: offset(reading.days_away),
            })}
          </span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onOdometerChange(u.distance.toInputValue(Number(reading.odometer_km)))}
          >
            {t('tireList.suggestionUse')}
          </Button>
        </div>
      ) : reading === null ? (
        <p className="text-sm text-text-mute">{t('tireList.suggestionNone')}</p>
      ) : null}
    </div>
  )
}
