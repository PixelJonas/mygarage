/**
 * A picker for the canonical maintenance type of a rule, reminder or line
 * item. The options come from the backend registry; the labels are
 * translated by code with the registry's English as the fallback, so a code
 * the locale does not know still reads as words.
 *
 * Blank means "let the backend classify from the description", which it
 * does conservatively (two candidate types, or none, leave it untyped).
 */

import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Select } from './ui'
import { useMaintenanceTypes } from '../hooks/useReminders'

interface MaintenanceTypeSelectProps {
  id: string
  value: string | null | undefined
  onChange: (code: string | undefined) => void
  disabled?: boolean
  /** The placeholder for the blank option; defaults to "auto-detect". */
  blankLabel?: string
  className?: string
}

export default function MaintenanceTypeSelect({
  id,
  value,
  onChange,
  disabled,
  blankLabel,
  className,
}: MaintenanceTypeSelectProps) {
  const { t } = useTranslation('vehicles')
  const { data } = useMaintenanceTypes()
  const options = useMemo(() => {
    const types = data ?? []
    const list = types.map((mt) => ({
      value: mt.code,
      label: t(`maintenanceTypes.${mt.code}`, { defaultValue: mt.label }),
    }))
    // A code from a pack the registry does not list still has to be selectable
    // so an existing value is never silently dropped on save.
    if (value && !types.some((mt) => mt.code === value)) {
      list.push({ value, label: value })
    }
    return list
  }, [data, value, t])
  return (
    <Select
      id={id}
      value={value ?? ''}
      onChange={(e) => onChange(e.target.value || undefined)}
      disabled={disabled}
      placeholder={blankLabel ?? t('maintenanceTypeSelect.auto')}
      options={options}
      className={className}
    />
  )
}
