import { useTranslation } from 'react-i18next'

import { useNearestOdometer } from '../../hooks/queries/useOdometerRecords'
import { useUnitFormat } from '../../hooks/useUnitFormat'
import { formatDateForDisplay } from '../../utils/dateUtils'
import { seedUnitField, type UnitFieldOrigin } from '../../utils/unitFormat'
import { Button, Field, Input } from '../ui'

/**
 * An odometer as typed, with the canonical value it was seeded from.
 *
 * A single value rather than a typed string plus a sibling origin: keeping
 * them in one object means a reset can never clear one and forget the other,
 * and typing can never drop the origin it has to keep carrying forward. See
 * `utils/unitFormat.ts` for what the origin is for.
 */
export interface OdometerFieldValue {
  typed: string
  origin: UnitFieldOrigin
}

/** A blank odometer field, with no canonical origin to preserve. */
export const EMPTY_ODOMETER: OdometerFieldValue = {
  typed: '',
  origin: { canonical: null, display: '' },
}

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
  /** The odometer as typed, in the user's distance unit, with the canonical
   *  value it was last seeded from. */
  odometer: OdometerFieldValue
  onOdometerChange: (next: OdometerFieldValue) => void
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
 * sit on the far side of it, and only the user can judge that. Use seeds the
 * field from the reading's own canonical value, not from a re-conversion of
 * its rounded display string: on imperial units, accepting a suggestion for
 * a tire mounted at 100,000 km used to store 99,999.56 km, because the
 * "62,137 mi" it displayed was converted back to kilometres with no memory of
 * the value it came from. Typing keeps carrying the current origin forward
 * unchanged -- only Use ever replaces it -- so `canonicalFromUnitField` can
 * still tell an untouched field from an edited one after a suggestion has
 * been accepted.
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
          value={odometer.typed}
          onChange={(e) => onOdometerChange({ typed: e.target.value, origin: odometer.origin })}
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
            onClick={() => {
              const seed = seedUnitField(Number(reading.odometer_km), u.distance)
              onOdometerChange({ typed: seed.display, origin: seed })
            }}
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
