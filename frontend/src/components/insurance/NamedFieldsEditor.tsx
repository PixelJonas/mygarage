import { Plus, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useFieldArray, type Control, type UseFormRegister } from 'react-hook-form'
import type { InsuranceFormData } from '../../schemas/insurance'
import { Chip, IconButton, Input } from '../ui'

type FieldsPath = 'fields' | `vehicles.${number}.fields`

interface NamedFieldsEditorProps {
  control: Control<InsuranceFormData>
  register: UseFormRegister<InsuranceFormData>
  name: FieldsPath
  /** i18n keys of labels offered as one-tap chips. */
  suggestions: readonly string[]
  disabled?: boolean
  /** Distinguishes the inputs of several editors on one form. */
  idPrefix: string
}

/**
 * User-named label/value pairs. Most policies carry the same handful of
 * details, so the common ones are one tap; anything else is typed.
 */
export default function NamedFieldsEditor({
  control,
  register,
  name,
  suggestions,
  disabled = false,
  idPrefix,
}: NamedFieldsEditorProps) {
  const { t } = useTranslation('forms')
  const { fields, append, remove } = useFieldArray({ control, name })
  const used = new Set(fields.map((field) => field.label))
  const offered = suggestions.map((key) => t(key)).filter((label) => !used.has(label))

  return (
    <div className="space-y-2">
      {fields.map((field, index) => (
        <div key={field.id} className="flex gap-2 items-start">
          <Input
            id={`${idPrefix}-label-${index}`}
            aria-label={t('insurance.fieldLabel')}
            placeholder={t('insurance.fieldLabel')}
            {...register(`${name}.${index}.label` as const)}
            disabled={disabled}
            className="flex-1"
          />
          <Input
            id={`${idPrefix}-value-${index}`}
            aria-label={t('insurance.fieldValue')}
            placeholder={t('insurance.fieldValue')}
            {...register(`${name}.${index}.value` as const)}
            disabled={disabled}
            className="flex-1"
          />
          <IconButton
            icon={X}
            label={t('insurance.removeField')}
            variant="ghost"
            size="sm"
            disabled={disabled}
            onClick={() => remove(index)}
          />
        </div>
      ))}
      <div className="flex flex-wrap gap-2">
        {offered.map((label) => (
          <Chip key={label} icon={Plus} onClick={() => append({ label, value: '' })}>
            {label}
          </Chip>
        ))}
        <Chip icon={Plus} tone="accent" onClick={() => append({ label: '', value: '' })}>
          {t('insurance.addCustomField')}
        </Chip>
      </div>
    </div>
  )
}
