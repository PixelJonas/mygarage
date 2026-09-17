/**
 * Apply a reminder pack with a preview first.
 *
 * The backend computes, without writing, what applying would do per item:
 * the rule it reuses or creates, the service the reminder would count from
 * ("Existing maintenance history found"), the loose reminders it adopts or
 * supersedes, and the resulting due values. The owner can point an item at
 * an untyped line item (which types it) or say the work was done today, and
 * then confirm. Nothing is written until Apply.
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Package } from 'lucide-react'
import { toast } from 'sonner'
import FormModalWrapper from './FormModalWrapper'
import { Button, Chip, Mono } from './ui'
import { describeDue } from './RecurrenceFields'
import { useApplyPack, usePackPreview } from '../hooks/useReminders'
import { useUnitFormat } from '../hooks/useUnitFormat'
import { useDateLocale } from '../hooks/useDateLocale'
import { formatDateForDisplay } from '../utils/dateUtils'
import { getActionErrorMessage } from '../utils/httpErrorHandler'
import type { AnchorChoices } from '../services/reminderService'
import type { AnchorCandidate, AnchorChoice, PackItemPlan } from '../types/reminder'

interface ApplyPackDialogProps {
  vin: string
  packId: string
  packName: string
  onClose: () => void
  onApplied: () => void
}

export default function ApplyPackDialog({ vin, packId, packName, onClose, onApplied }: ApplyPackDialogProps) {
  const { t } = useTranslation('vehicles')
  const u = useUnitFormat()
  const dateLocale = useDateLocale()
  const [anchors, setAnchors] = useState<AnchorChoices>({})
  const [error, setError] = useState<string | null>(null)
  const { data: preview, isLoading, error: previewError } = usePackPreview(vin, packId, anchors)
  const applyMutation = useApplyPack(vin)

  const fmtDate = (value: string | null | undefined) =>
    value ? formatDateForDisplay(value, undefined, dateLocale) : null
  const fmtKm = (value: string | number | null | undefined) =>
    value == null ? null : u.distance.format(Number(value))

  /** `undefined` keeps the backend's proposal; anything else is sent as given. */
  const setChoice = (key: string, choice: AnchorChoice | undefined) => {
    setAnchors((prev) => {
      const next = { ...prev }
      if (choice) next[key] = choice
      else delete next[key]
      return next
    })
  }

  const handleApply = async () => {
    setError(null)
    try {
      await applyMutation.mutateAsync({ packId, anchors })
      toast.success(t('reminderList.packApplied'))
      onApplied()
    } catch (err) {
      setError(getActionErrorMessage(err, t('applyPack.action')))
    }
  }

  const candidateLabel = (c: AnchorCandidate) =>
    [fmtDate(c.date), fmtKm(c.odometer_km), c.description].filter(Boolean).join(' · ')

  const renderItem = (item: PackItemPlan) => {
    const choice = anchors[item.key] ?? undefined
    const supersedes = item.supersede_reminder_ids ?? []
    const untyped = item.untyped_candidates ?? []
    const due = describeDue(item, (km) => u.distance.format(km), (iso) => fmtDate(iso) ?? '', t)
    return (
      <li key={item.key} className="rounded-lg border border-border bg-surface-2 p-3 space-y-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <span className="text-sm font-medium text-text">{item.title}</span>
          <Chip tone={item.rule_action === 'skip' ? 'warning' : 'default'}>
            {t(`applyPack.ruleAction.${item.rule_action}`)}
          </Chip>
        </div>
        {item.rule_action === 'skip' ? (
          <p className="text-xs text-warning">{t('applyPack.skipTwoRules')}</p>
        ) : (
          <>
            {item.anchor?.origin === 'history' && item.anchor.kind === 'service' && (
              <p className="text-xs text-text">
                {t('applyPack.historyFound')}{' '}
                <Mono size="xs" tone="muted">
                  {[fmtDate(item.anchor.date), fmtKm(item.anchor.odometer_km)].filter(Boolean).join(' · ')}
                </Mono>
              </p>
            )}
            {item.keep_reminder_id != null && (
              <p className="text-xs text-text-mute">
                {item.adopted ? t('applyPack.adopts') : t('applyPack.keepsExisting')}
                {supersedes.length > 0 && ` ${t('applyPack.supersedes', { count: supersedes.length })}`}
              </p>
            )}
            {item.newer_service && (
              <p className="text-xs text-text-mute">
                {t('applyPack.newerService', { when: candidateLabel(item.newer_service) })}
              </p>
            )}
            {item.anchor?.note && <p className="text-xs text-text-mute">{t(`applyPack.notes.${item.anchor.origin}`)}</p>}
            <fieldset className="space-y-1">
              <legend className="text-xs font-medium text-text-mute">{t('applyPack.countFrom')}</legend>
              <label className="flex items-center gap-2 text-xs text-text">
                <input
                  type="radio"
                  name={`anchor-${item.key}`}
                  checked={!choice}
                  onChange={() => setChoice(item.key, undefined)}
                />
                {t('applyPack.choiceProposed')}
              </label>
              {untyped.map((c) => (
                <label key={c.line_item_id} className="flex items-center gap-2 text-xs text-text">
                  <input
                    type="radio"
                    name={`anchor-${item.key}`}
                    checked={choice?.line_item_id === c.line_item_id}
                    onChange={() => setChoice(item.key, { done_today: false, line_item_id: c.line_item_id })}
                  />
                  {t('applyPack.choiceLineItem', { label: candidateLabel(c) })}
                </label>
              ))}
              <label className="flex items-center gap-2 text-xs text-text">
                <input
                  type="radio"
                  name={`anchor-${item.key}`}
                  checked={!!choice?.done_today}
                  onChange={() => setChoice(item.key, { done_today: true })}
                />
                {t('applyPack.choiceDoneToday')}
              </label>
            </fieldset>
            {due && (
              <p className="text-xs text-text">
                {t('reminderList.due')}: <Mono size="xs" tone="accent">{due}</Mono>
              </p>
            )}
          </>
        )}
      </li>
    )
  }

  return (
    <FormModalWrapper
      title={t('applyPack.title', { pack: packName })}
      icon={Package}
      onClose={onClose}
      width="md"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={applyMutation.isPending}>
            {t('common:cancel')}
          </Button>
          <Button
            onClick={() => void handleApply()}
            loading={applyMutation.isPending}
            disabled={applyMutation.isPending || !preview}
          >
            {t('reminderList.applyPack')}
          </Button>
        </>
      }
    >
      <div className="p-6 space-y-4">
        <p className="text-sm text-text-mute">{t('applyPack.intro')}</p>
        {error && (
          <p role="alert" className="text-sm text-danger bg-danger/10 border border-danger rounded-lg p-3">
            {error}
          </p>
        )}
        {isLoading && <p className="text-sm text-text-mute">{t('applyPack.loading')}</p>}
        {previewError && <p role="alert" className="text-sm text-danger">{t('applyPack.previewFailed')}</p>}
        {preview && <ul className="space-y-3">{preview.items.map(renderItem)}</ul>}
      </div>
    </FormModalWrapper>
  )
}
