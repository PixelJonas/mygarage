import { useTranslation } from 'react-i18next'
import {
  useWatch,
  type Control,
  type FieldErrors,
  type UseFormRegister,
  type UseFormSetValue,
} from 'react-hook-form'
import type { CoverageFormData, InsuranceFormData } from '../../schemas/insurance'
import type { CoverageKey } from '../../types/insurance'
import { COVERAGES, coverageSlots } from '../../constants/insuranceCoverages'
import { Checkbox, Field, NumberInput, registerDecimal } from '../ui'

type CoveragesPath = `vehicles.${number}.coverages`
type CoverageErrors = NonNullable<
  NonNullable<FieldErrors<InsuranceFormData>['vehicles']>[number]
>['coverages']

interface CoverageEditorProps {
  control: Control<InsuranceFormData>
  register: UseFormRegister<InsuranceFormData>
  setValue: UseFormSetValue<InsuranceFormData>
  name: CoveragesPath
  disabled?: boolean
  /** Distinguishes the inputs of several vehicles' editors on one form. */
  idPrefix: string
  /** This vehicle's coverage errors, already narrowed by the caller. */
  errors?: CoverageErrors
}

/**
 * The standard coverage checklist: one row per catalogue coverage, always in
 * catalogue order, always the same rows for every vehicle on every policy.
 *
 * TICKING THE BOX is what says the coverage is carried; the amounts are how
 * much, and every one of them is optional. So roadside assistance with nothing
 * typed is a complete, meaningful answer, and a coverage left unticked is
 * simply not on the policy.
 *
 * An unticked row stays one line. The amounts appear only once a coverage is
 * on the policy, which keeps thirteen coverages short on screen when a vehicle
 * carries four of them. Which amounts those are comes from `coverageSlots`,
 * never from a branch here, so the form can never offer an input the API
 * would reject or miss one it expects.
 */
export default function CoverageEditor({
  control,
  register,
  setValue,
  name,
  disabled = false,
  idPrefix,
  errors,
}: CoverageEditorProps) {
  const { t } = useTranslation('forms')
  const rows = (useWatch({ control, name }) ?? []) as CoverageFormData[]

  return (
    <fieldset className="space-y-1">
      <legend className="text-xs font-semibold uppercase tracking-wide text-text-mute mb-2">
        {t('insurance.coverages')}
      </legend>
      {rows.map((row, position) => {
        const key = row?.coverage_key as CoverageKey
        const meta = COVERAGES[key]
        if (!meta) return null
        const included = !!row?.included
        const rowErrors = errors?.[position]
        const { onChange, ...tick } = register(`${name}.${position}.included`)

        return (
          <div key={key} className={`rounded-lg px-3 py-2 ${included ? 'bg-surface-2' : ''}`}>
            <Checkbox
              id={`${idPrefix}-${key}`}
              label={t(meta.labelKey)}
              disabled={disabled}
              {...tick}
              onChange={async (event) => {
                await onChange(event)
                // Untick and the amounts go with it. Left behind, an invalid
                // one keeps blocking the save from a row that is no longer
                // on screen to show its error.
                if (!event.target.checked) {
                  for (const [slotName] of coverageSlots(key)) {
                    setValue(`${name}.${position}.${slotName}`, undefined, {
                      shouldValidate: true,
                    })
                  }
                }
              }}
            />
            {included && (
              <div className="mt-2 grid gap-3 grid-cols-[repeat(auto-fill,minmax(9rem,1fr))]">
                {coverageSlots(key).map(([slotName, slot]) => {
                  const id = `${idPrefix}-${key}-${slotName}`
                  const error = rowErrors?.[slotName]?.message
                  return (
                    <Field key={slotName} id={id} label={t(slot.labelKey)} error={error}>
                      <NumberInput
                        id={id}
                        {...registerDecimal(register, `${name}.${position}.${slotName}`)}
                        invalid={!!error}
                        disabled={disabled}
                      />
                    </Field>
                  )
                })}
                {meta.hintKey && !meta.primary && (
                  <p className="text-xs text-text-mute self-end pb-2">{t(meta.hintKey)}</p>
                )}
              </div>
            )}
          </div>
        )
      })}
    </fieldset>
  )
}
