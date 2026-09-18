/**
 * Snooze a pending reminder: hide it from every overdue/upcoming count and
 * notification until a date, without touching the due thresholds. On the
 * chosen date the reminder is back with whatever overdue state reality gives
 * it. Presets are one tap and submit immediately; the custom date needs the
 * confirm button. An already-snoozed reminder gets an Unsnooze action here.
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Clock } from 'lucide-react'
import { toast } from 'sonner'
import FormModalWrapper from './FormModalWrapper'
import { Button, Field, Input } from './ui'
import { useSnoozeReminder, useUnsnoozeReminder } from '../hooks/useReminders'
import { addDaysToIsoDate, addMonthsToIsoDate } from '../utils/dateUtils'
import { todayInHousehold } from '../constants/i18n'
import { getActionErrorMessage } from '../utils/httpErrorHandler'
import type { Reminder } from '../types/reminder'

interface SnoozeReminderDialogProps {
  vin: string
  reminder: Reminder
  onClose: () => void
  /** Fired after a successful snooze or unsnooze, before closing. */
  onSuccess: () => void
}

export default function SnoozeReminderDialog({
  vin,
  reminder,
  onClose,
  onSuccess,
}: SnoozeReminderDialogProps) {
  const { t } = useTranslation('vehicles')
  const snoozeMutation = useSnoozeReminder(vin)
  const unsnoozeMutation = useUnsnoozeReminder(vin)
  const today = todayInHousehold()
  const [customUntil, setCustomUntil] = useState(reminder.snoozed_until ?? '')
  const [error, setError] = useState<string | null>(null)
  const submitting = snoozeMutation.isPending || unsnoozeMutation.isPending
  const snoozedNow = reminder.snoozed_until != null && today < reminder.snoozed_until

  const snoozeTo = async (until: string): Promise<void> => {
    setError(null)
    try {
      await snoozeMutation.mutateAsync({ id: reminder.id, until })
      toast.success(t('reminderList.snoozed'))
      onSuccess()
    } catch (err) {
      setError(getActionErrorMessage(err, t('reminderList.snoozeAction')))
    }
  }

  const handleUnsnooze = async (): Promise<void> => {
    setError(null)
    try {
      await unsnoozeMutation.mutateAsync(reminder.id)
      toast.success(t('reminderList.unsnoozed'))
      onSuccess()
    } catch (err) {
      setError(getActionErrorMessage(err, t('reminderList.unsnoozeAction')))
    }
  }

  return (
    <FormModalWrapper title={t('reminderList.snoozeTitle')} icon={Clock} onClose={onClose} width="sm">
      <div className="space-y-4">
        <p className="text-sm text-text-mute">{t('reminderList.snoozeExplain')}</p>

        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={submitting}
            onClick={() => void snoozeTo(addDaysToIsoDate(today, 7))}
          >
            {t('reminderList.snoozeWeek')}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={submitting}
            onClick={() => void snoozeTo(addMonthsToIsoDate(today, 1))}
          >
            {t('reminderList.snoozeMonth')}
          </Button>
        </div>

        <div className="flex items-end gap-2">
          <div className="flex-1">
            <Field id="snooze-until" label={t('reminderList.snoozeCustomLabel')}>
              <Input
                id="snooze-until"
                type="date"
                value={customUntil}
                min={addDaysToIsoDate(today, 1)}
                onChange={(e) => setCustomUntil(e.target.value)}
              />
            </Field>
          </div>
          <Button
            variant="primary"
            size="sm"
            disabled={submitting || !customUntil || customUntil <= today}
            onClick={() => void snoozeTo(customUntil)}
          >
            {t('reminderList.snoozeConfirm')}
          </Button>
        </div>

        {snoozedNow && (
          <Button variant="secondary" size="sm" disabled={submitting} onClick={() => void handleUnsnooze()}>
            {t('reminderList.unsnooze')}
          </Button>
        )}

        {error && <p className="text-sm text-danger">{error}</p>}
      </div>
    </FormModalWrapper>
  )
}
