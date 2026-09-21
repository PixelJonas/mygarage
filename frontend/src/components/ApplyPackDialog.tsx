/**
 * Apply a reminder pack with a preview first.
 *
 * The backend computes, without writing, what applying would do per item:
 * the rule it reuses or creates, the service the reminder would count from
 * ("Existing maintenance history found"), the loose reminders it adopts or
 * supersedes, and the resulting due values. The owner can point an item at
 * an untyped line item (which types it) or say the work was done today, and
 * then confirm. Nothing is written until Apply.
 *
 * The intervals are editable here too (issue #165: "define a standard, and then
 * override it upon creating a reminder"). An override is not a display tweak: it
 * is re-previewed, because the plan reads the intervals and the anchor proposal
 * or a skip reason can change with them. So Apply waits for the preview to catch
 * up rather than acting on a stale plan.
 */

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Package } from 'lucide-react'
import { toast } from 'sonner'
import FormModalWrapper from './FormModalWrapper'
import { Button, Chip, Field, Mono, NumberInput } from './ui'
import { describeDue } from './RecurrenceFields'
import { useApplyPack, usePackPreview } from '../hooks/useReminders'
import { useUnitFormat } from '../hooks/useUnitFormat'
import { useDateLocale } from '../hooks/useDateLocale'
import { formatDateForDisplay } from '../utils/dateUtils'
import { getActionErrorMessage } from '../utils/httpErrorHandler'
import { canonicalFromUnitField, seedUnitField } from '../utils/unitFormat'
import { parseDecimalInput } from '../utils/decimalInput'
import { getActiveLocale } from '../constants/i18n'
import type { AnchorChoices, IntervalOverrides } from '../services/reminderService'
import type { AnchorCandidate, AnchorChoice, PackItemPlan } from '../types/reminder'

/** Whole-number interval fields, with the label the rule form already uses. */
const COUNT_FIELDS = [
  ['interval_months', 'forms:recurrence.everyMonths'],
  ['interval_days', 'forms:recurrence.everyDays'],
  ['interval_hours', 'forms:recurrence.everyHours'],
] as const

type OverrideDraft = NonNullable<IntervalOverrides[string]>

/** A wire decimal as a number. Money and intervals arrive as strings so no
 *  precision is lost in transit; the unit helpers and the inputs want numbers. */
const num = (value: string | number | null | undefined): number | null =>
  value == null ? null : Number(value)

/** Debounce a value so typing does not fire a preview request per keystroke. */
function useDebounced<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms)
    return () => clearTimeout(timer)
  }, [value, ms])
  return settled
}

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
  const [overrides, setOverrides] = useState<IntervalOverrides>({})
  const [error, setError] = useState<string | null>(null)
  // The typed text per item per field, kept beside the parsed override so a
  // half-typed "10." survives a re-render and a locale separator is not eaten.
  const [drafts, setDrafts] = useState<Record<string, Record<string, string>>>({})
  const settledOverrides = useDebounced(overrides, 300)
  const settling = settledOverrides !== overrides
  const {
    data: preview,
    isLoading,
    error: previewError,
    isFetching,
  } = usePackPreview(vin, packId, anchors, settledOverrides)
  const applyMutation = useApplyPack(vin)
  // Applying against a plan that has not caught up is how a skip reason gets
  // ignored, so the button waits for both the debounce and the refetch.
  const planIsStale = settling || isFetching

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

  /**
   * Patch one interval of one item.
   *
   * Seeded from the item's CURRENT planned values, because an override replaces
   * all four intervals at once: sending only the field that changed would null
   * the others and quietly turn a distance-and-calendar rule into a
   * distance-only one.
   *
   * Clearing every field drops the override entirely rather than sending an
   * empty one. The schema refuses that (a rule with no interval cannot exist),
   * and reverting to the pack's value is the only other reading of "I cleared
   * it all".
   */
  const patchOverride = (item: PackItemPlan, field: keyof OverrideDraft, raw: number | null) => {
    setOverrides((prev) => {
      const base: OverrideDraft =
        prev[item.key] ?? {
          interval_km: num(item.interval_km),
          interval_months: item.interval_months ?? null,
          interval_days: item.interval_days ?? null,
          interval_hours: num(item.interval_hours),
        }
      const next: OverrideDraft = { ...base, [field]: raw }
      const copy = { ...prev }
      if (Object.values(next).some((v) => v != null)) copy[item.key] = next
      else delete copy[item.key]
      return copy
    })
  }

  const setDraft = (key: string, field: string, text: string) =>
    setDrafts((prev) => ({ ...prev, [key]: { ...prev[key], [field]: text } }))

  const handleApply = async () => {
    setError(null)
    try {
      await applyMutation.mutateAsync({ packId, anchors, overrides })
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
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {item.interval_km != null && (
                <Field
                  id={`override-${item.key}-km`}
                  label={t('forms:recurrence.everyDistance')}
                  unit={u.distance.label}
                >
                  <NumberInput
                    id={`override-${item.key}-km`}
                    value={
                      drafts[item.key]?.interval_km ??
                      seedUnitField(num(item.interval_km), u.distance).display
                    }
                    onChange={(e) => {
                      setDraft(item.key, 'interval_km', e.target.value)
                      // Through the same helpers the rule form uses, so a
                      // vehicle in miles types miles and the API still gets km.
                      const km = canonicalFromUnitField(
                        e.target.value,
                        seedUnitField(num(item.interval_km), u.distance),
                        u.distance,
                      )
                      patchOverride(item, 'interval_km', km ?? null)
                    }}
                    disabled={applyMutation.isPending}
                  />
                </Field>
              )}
              {COUNT_FIELDS.filter(([field]) => item[field] != null).map(([field, labelKey]) => (
                <Field key={field} id={`override-${item.key}-${field}`} label={t(labelKey)}>
                  <NumberInput
                    id={`override-${item.key}-${field}`}
                    value={drafts[item.key]?.[field] ?? String(item[field] ?? '')}
                    onChange={(e) => {
                      setDraft(item.key, field, e.target.value)
                      const parsed = parseDecimalInput(e.target.value, getActiveLocale())
                      patchOverride(item, field, parsed.kind === 'value' ? parsed.value : null)
                    }}
                    disabled={applyMutation.isPending}
                  />
                </Field>
              ))}
            </div>
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
            disabled={applyMutation.isPending || !preview || planIsStale}
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
        {!isLoading && planIsStale && (
          <p className="text-sm text-text-mute">{t('applyPack.recalculating')}</p>
        )}
        {previewError && <p role="alert" className="text-sm text-danger">{t('applyPack.previewFailed')}</p>}
        {preview && <ul className="space-y-3">{preview.items.map(renderItem)}</ul>}
      </div>
    </FormModalWrapper>
  )
}
