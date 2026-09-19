import { useTranslation } from 'react-i18next'
import { useMemo, useState } from 'react'
import { useFieldArray, useForm, useWatch, type Resolver } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Save, FileUp, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import FormModalWrapper from '../FormModalWrapper'
import {
  Button,
  Field,
  IconButton,
  Input,
  NumberInput,
  Select,
  Textarea,
  registerDecimal,
} from '../ui'
import type {
  InsurancePDFParseResponse,
  InsurancePolicy,
  InsurancePolicyCreate,
  NamedField,
  PolicyVehicleCreate,
} from '../../types/insurance'
import {
  makeInsuranceSchema,
  type InsuranceFormData,
  type PolicyVehicleFormData,
  POLICY_TYPES,
  PREMIUM_FREQUENCIES,
  SUGGESTED_POLICY_FIELDS,
  SUGGESTED_VEHICLE_FIELDS,
} from '../../schemas/insurance'
import InsurancePDFUpload from '../InsurancePDFUpload'
import NamedFieldsEditor from './NamedFieldsEditor'
import {
  useCreateInsurancePolicy,
  useReplaceInsurancePolicy,
  useUpdateInsurancePolicy,
} from '../../hooks/queries/useInsuranceRecords'
import { useQuickEntryVehicles } from '../../hooks/queries/useQuickEntryVehicles'
import { vehicleLabel } from '../../utils/vehicleLabel'
import { formatDateForInput } from '../../utils/dateUtils'
import { formatCurrency } from '../../utils/formatUtils'
import { useCurrencyPreference } from '../../hooks/useCurrencyPreference'
import { applyServerErrors } from '../../hooks/useApiFormErrors'
import { getActionErrorMessage } from '../../utils/httpErrorHandler'

export type PolicyFormMode = 'create' | 'edit' | 'replace'

interface PolicyFormProps {
  mode: PolicyFormMode
  /** edit: the policy being edited. replace: the policy being replaced. */
  policy?: InsurancePolicy
  /** create from a vehicle's tab: that vehicle starts attached. */
  initialVin?: string
  onClose: () => void
  onSuccess: () => void
}

const POLICY_TYPE_VALUES: readonly string[] = POLICY_TYPES.map((option) => option.value)

function emptyVehicle(vin: string, over: Partial<PolicyVehicleFormData> = {}): PolicyVehicleFormData {
  return {
    vin,
    policy_type: '',
    premium_share: undefined,
    deductible: undefined,
    coverage_limits: '',
    notes: '',
    effective_to: '',
    fields: [],
    ...over,
  }
}

const cleanFields = (fields: NamedField[]): NamedField[] =>
  fields.map((field) => ({ label: field.label.trim(), value: field.value.trim() }))

export default function PolicyForm({ mode, policy, initialVin, onClose, onSuccess }: PolicyFormProps) {
  const { t } = useTranslation('forms')
  const isEdit = mode === 'edit'
  const isReplace = mode === 'replace'
  const createMutation = useCreateInsurancePolicy()
  const updateMutation = useUpdateInsurancePolicy()
  const replaceMutation = useReplaceInsurancePolicy()
  const { data: garage = [] } = useQuickEntryVehicles()
  const { currencyCode, locale } = useCurrencyPreference()
  const [showPDFUpload, setShowPDFUpload] = useState(false)
  const [pickedVin, setPickedVin] = useState('')
  const [endOldOn, setEndOldOn] = useState('')

  // A creator can hold a policy that covers vehicles they can no longer see.
  // Sending a vehicle list would then REMOVE the hidden ones, so the vehicle
  // editor is locked and `vehicles` is left out of the save entirely.
  const vehiclesLocked = isEdit && (policy?.other_vehicle_count ?? 0) > 0

  // Zod bakes its messages in at construction, so the schema is rebuilt when
  // the language changes. Only the resolver depends on it, so a rebuild can't
  // discard what the user typed.
  const schema = useMemo(() => makeInsuranceSchema(t), [t])

  const startingVehicles: PolicyVehicleFormData[] = useMemo(() => {
    if (isEdit && policy) {
      return (policy.vehicles ?? []).map((vehicle) =>
        emptyVehicle(vehicle.vin, {
          policy_type: vehicle.policy_type,
          premium_share: vehicle.premium_share != null ? Number(vehicle.premium_share) : undefined,
          deductible: vehicle.deductible != null ? Number(vehicle.deductible) : undefined,
          coverage_limits: vehicle.coverage_limits ?? '',
          notes: vehicle.notes ?? '',
          effective_to: vehicle.effective_to ?? '',
          fields: (vehicle.fields ?? []).map((field) => ({ ...field })),
        })
      )
    }
    if (isReplace && policy) {
      // A new insurer's coverages differ: carry the vehicles, not their terms.
      return (policy.vehicles ?? [])
        .filter((vehicle) => !vehicle.effective_to)
        .map((vehicle) => emptyVehicle(vehicle.vin, { policy_type: vehicle.policy_type }))
    }
    return initialVin ? [emptyVehicle(initialVin)] : []
  }, [isEdit, isReplace, policy, initialVin])

  const {
    register,
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
    setValue,
    setError: setFieldError,
  } = useForm<InsuranceFormData>({
    resolver: zodResolver(schema) as Resolver<InsuranceFormData>,
    defaultValues: {
      provider: isEdit ? (policy?.provider ?? '') : '',
      policy_number: isEdit ? (policy?.policy_number ?? '') : '',
      start_date: isEdit
        ? formatDateForInput(policy?.start_date)
        : isReplace
          ? formatDateForInput(policy?.end_date)
          : '',
      end_date: isEdit ? formatDateForInput(policy?.end_date) : '',
      premium_amount:
        isEdit && policy?.premium_amount != null ? Number(policy.premium_amount) : undefined,
      premium_frequency: (isEdit || isReplace ? policy?.premium_frequency : undefined) ?? undefined,
      notes: isEdit ? (policy?.notes ?? '') : '',
      fields: isEdit && policy ? (policy.fields ?? []).map((field) => ({ ...field })) : [],
      vehicles: startingVehicles,
    },
  })

  const { fields: vehicleRows, append, remove } = useFieldArray({ control, name: 'vehicles' })
  const watchedVehicles = useWatch({ control, name: 'vehicles' })
  const watchedPremium = useWatch({ control, name: 'premium_amount' })

  const nameByVin = useMemo(() => {
    const names = new Map<string, string>()
    for (const vehicle of garage) names.set(vehicle.vin, vehicleLabel(vehicle))
    for (const vehicle of policy?.vehicles ?? []) {
      if (!names.has(vehicle.vin)) names.set(vehicle.vin, vehicle.vehicle_name)
    }
    return names
  }, [garage, policy])

  const attached = new Set(vehicleRows.map((row) => row.vin))
  const pickable = garage.filter((vehicle) => !attached.has(vehicle.vin))

  // What an untouched share input will resolve to, mirrored from the backend's
  // rule so the placeholder tells the truth: the premium, less every explicit
  // share, split evenly across the vehicles with no share of their own.
  const premium = typeof watchedPremium === 'number' ? watchedPremium : Number(watchedPremium)
  const explicit = (watchedVehicles ?? []).map((vehicle) => {
    const share = vehicle?.premium_share as unknown
    if (share === undefined || share === null || share === '') return null
    const parsed = typeof share === 'number' ? share : Number(String(share).replace(',', '.'))
    return Number.isFinite(parsed) ? parsed : null
  })
  const allocated = explicit.reduce<number>((sum, share) => sum + (share ?? 0), 0)
  const unsetCount = explicit.filter((share) => share === null).length
  const hasPremium = Number.isFinite(premium) && watchedPremium !== undefined && watchedPremium !== null
  const evenSplit = hasPremium && unsetCount > 0 ? Math.max(premium - allocated, 0) / unsetCount : null
  const overAllocated = hasPremium && allocated > premium + 0.004
  const underAllocated =
    hasPremium && unsetCount === 0 && explicit.length > 0 && Math.abs(allocated - premium) > 0.004
  const money = (value: number): string => formatCurrency(value, { currencyCode, locale })

  const addVehicle = () => {
    if (!pickedVin) return
    append(emptyVehicle(pickedVin))
    setPickedVin('')
  }

  const handlePDFDataExtracted = (parsed: InsurancePDFParseResponse) => {
    const data = parsed.data
    if (data.provider) setValue('provider', data.provider)
    if (data.policy_number) setValue('policy_number', data.policy_number)
    if (data.start_date) setValue('start_date', data.start_date)
    if (data.end_date) setValue('end_date', data.end_date)
    if (data.premium_amount) setValue('premium_amount', Number(data.premium_amount))
    if (data.premium_frequency) setValue('premium_frequency', data.premium_frequency)
    if (data.notes) setValue('notes', data.notes)

    const parsedType =
      data.policy_type && POLICY_TYPE_VALUES.includes(data.policy_type) ? data.policy_type : ''
    const already = new Set(vehicleRows.map((row) => row.vin))
    for (const vehicle of parsed.vehicles) {
      if (!vehicle.matched || already.has(vehicle.vin)) continue
      append(
        emptyVehicle(vehicle.vin, {
          policy_type: parsedType,
          premium_share: vehicle.premium_share ? Number(vehicle.premium_share) : undefined,
          deductible: vehicle.deductible ? Number(vehicle.deductible) : undefined,
          coverage_limits: data.coverage_limits ?? '',
        })
      )
    }
  }

  const onSubmit = async (data: InsuranceFormData) => {
    try {
      // null, never '', for a cleared optional: every field here is mounted,
      // so an explicit null correctly clears the column (#140).
      const vehicles = data.vehicles.map((vehicle) => ({
        vin: vehicle.vin,
        policy_type: vehicle.policy_type as PolicyVehicleCreate['policy_type'],
        premium_share: vehicle.premium_share ?? null,
        deductible: vehicle.deductible ?? null,
        coverage_limits: vehicle.coverage_limits || null,
        notes: vehicle.notes || null,
        effective_to: vehicle.effective_to || null,
        fields: cleanFields(vehicle.fields),
      }))
      const base = {
        provider: data.provider,
        policy_number: data.policy_number,
        start_date: data.start_date,
        end_date: data.end_date,
        premium_amount: data.premium_amount ?? null,
        premium_frequency: (data.premium_frequency ||
          null) as InsurancePolicyCreate['premium_frequency'],
        notes: data.notes || null,
      }

      if (isReplace && policy) {
        await replaceMutation.mutateAsync({
          id: policy.id,
          ...base,
          vins: data.vehicles.map((vehicle) => vehicle.vin),
          end_old_on: endOldOn || null,
        })
      } else if (isEdit && policy) {
        await updateMutation.mutateAsync({
          id: policy.id,
          ...base,
          fields: cleanFields(data.fields),
          ...(vehiclesLocked ? {} : { vehicles }),
        })
      } else {
        await createMutation.mutateAsync({
          ...base,
          fields: cleanFields(data.fields),
          // Create has no mid-term removal: a vehicle joins for the whole term.
          vehicles: vehicles.map(({ effective_to: _unused, ...vehicle }) => vehicle),
        })
      }

      onSuccess()
      onClose()
    } catch (err) {
      // attached.length === 0 catches a non-422 failure (network drop, 500,
      // or the allocation rule's plain-text 422): it carries no field
      // problems, so `unhandled` alone would stay empty and nothing would show.
      const { attached: shown, unhandled } = applyServerErrors<InsuranceFormData>(
        setFieldError,
        err,
        ['provider', 'policy_number', 'start_date', 'end_date', 'premium_amount', 'premium_frequency', 'notes']
      )
      if (shown.length === 0 || unhandled.length > 0) {
        toast.error(getActionErrorMessage(err, t('insurance.saveAction')))
      }
    }
  }

  const title = isReplace
    ? t('insurance.switchTitle')
    : isEdit
      ? t('insurance.editTitle')
      : t('insurance.createTitle')

  return (
    <>
      <FormModalWrapper
        title={title}
        onClose={onClose}
        width="lg"
        footer={
          <>
            <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
              {t('common:cancel')}
            </Button>
            <Button
              type="submit"
              form="insurance-form"
              variant="primary"
              icon={Save}
              loading={isSubmitting}
              disabled={isSubmitting}
            >
              {isSubmitting ? t('common:saving') : isEdit ? t('common:update') : t('common:create')}
            </Button>
          </>
        }
      >
        <form id="insurance-form" onSubmit={handleSubmit(onSubmit)} className="p-6 space-y-5">
          {mode === 'create' && (
            <div>
              <Button
                type="button"
                variant="secondary"
                icon={FileUp}
                onClick={() => setShowPDFUpload(true)}
                className="w-full"
              >
                {t('insuranceForm.importFromPdf')}
              </Button>
              <p className="text-xs text-text-mute mt-2 text-center">{t('insurance.pdfUploadHint')}</p>
            </div>
          )}
          {isReplace && policy && (
            <p className="text-sm text-text-dim">
              {t('insurance.switchExplain', { provider: policy.provider })}
            </p>
          )}

          <div className="grid grid-cols-2 gap-4">
            <Field id="provider" label={t('insurance.provider')} required error={errors.provider}>
              <Input
                id="provider"
                type="text"
                {...register('provider')}
                placeholder={t('insuranceForm.providerPlaceholder')}
                invalid={!!errors.provider}
                disabled={isSubmitting}
              />
            </Field>
            <Field
              id="policy_number"
              label={t('insurance.policyNumber')}
              required
              error={errors.policy_number}
            >
              <Input
                id="policy_number"
                type="text"
                {...register('policy_number')}
                placeholder={t('insuranceForm.policyNumberPlaceholder')}
                invalid={!!errors.policy_number}
                disabled={isSubmitting}
              />
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Field id="start_date" label={t('common:startDate')} required error={errors.start_date}>
              <Input
                id="start_date"
                type="date"
                {...register('start_date')}
                invalid={!!errors.start_date}
                disabled={isSubmitting}
              />
            </Field>
            <Field id="end_date" label={t('common:endDate')} required error={errors.end_date}>
              <Input
                id="end_date"
                type="date"
                {...register('end_date')}
                invalid={!!errors.end_date}
                disabled={isSubmitting}
              />
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Field
              id="premium_amount"
              label={t('insurance.policyPremium')}
              hint={t('insurance.policyPremiumHint')}
              error={errors.premium_amount}
            >
              <NumberInput
                id="premium_amount"
                {...registerDecimal(register, 'premium_amount')}
                placeholder={t('insuranceForm.premiumAmountPlaceholder')}
                invalid={!!errors.premium_amount}
                disabled={isSubmitting}
              />
            </Field>
            <Field
              id="premium_frequency"
              label={t('insurance.premiumFrequency')}
              error={errors.premium_frequency}
            >
              <Select
                id="premium_frequency"
                {...register('premium_frequency')}
                disabled={isSubmitting}
                placeholder={t('insurance.selectFrequency')}
                options={PREMIUM_FREQUENCIES.map((option) => ({
                  value: option.value,
                  label: t(option.labelKey),
                }))}
              />
            </Field>
          </div>

          {isReplace && (
            <Field id="end_old_on" label={t('insurance.endOldOn')} hint={t('insurance.endOldOnHint')}>
              <Input
                id="end_old_on"
                type="date"
                value={endOldOn}
                onChange={(event) => setEndOldOn(event.target.value)}
                disabled={isSubmitting}
              />
            </Field>
          )}

          {!isReplace && (
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium text-text">{t('insurance.policyDetails')}</legend>
              <NamedFieldsEditor
                control={control}
                register={register}
                name="fields"
                suggestions={SUGGESTED_POLICY_FIELDS}
                disabled={isSubmitting}
                idPrefix="policy-field"
              />
            </fieldset>
          )}

          <fieldset className="space-y-3">
            <legend className="text-sm font-medium text-text">{t('insurance.coveredVehicles')}</legend>

            {vehiclesLocked ? (
              <p className="text-sm text-text-mute">{t('insurance.vehiclesLocked')}</p>
            ) : (
              <>
                {vehicleRows.length === 0 && (
                  <p className="text-sm text-text-mute">{t('insurance.noVehiclesYet')}</p>
                )}
                {vehicleRows.map((row, index) => {
                  const rowErrors = errors.vehicles?.[index]
                  return (
                    <div
                      key={row.id}
                      className="rounded-lg border border-border-soft bg-surface-2 p-4 space-y-3"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium text-text">
                          {nameByVin.get(row.vin) ?? row.vin}
                        </span>
                        <IconButton
                          icon={Trash2}
                          label={t('insurance.removeVehicle')}
                          variant="ghost"
                          size="sm"
                          disabled={isSubmitting}
                          onClick={() => remove(index)}
                        />
                      </div>
                      <div className={`grid gap-4 ${isReplace ? 'grid-cols-1' : 'grid-cols-3'}`}>
                        <Field
                          id={`vehicle-${index}-type`}
                          label={t('insurance.policyType')}
                          required
                          error={rowErrors?.policy_type}
                        >
                          <Select
                            id={`vehicle-${index}-type`}
                            {...register(`vehicles.${index}.policy_type`)}
                            disabled={isSubmitting}
                            invalid={!!rowErrors?.policy_type}
                            placeholder={t('common:selectType')}
                            options={POLICY_TYPES.map((option) => ({
                              value: option.value,
                              label: t(option.labelKey),
                            }))}
                          />
                        </Field>
                        {!isReplace && (
                          <>
                            <Field
                              id={`vehicle-${index}-share`}
                              label={t('insurance.vehicleShare')}
                              error={rowErrors?.premium_share}
                            >
                              <NumberInput
                                id={`vehicle-${index}-share`}
                                {...registerDecimal(register, `vehicles.${index}.premium_share`)}
                                placeholder={
                                  evenSplit != null
                                    ? t('insurance.evenSplit', { amount: money(evenSplit) })
                                    : t('insurance.evenSplitUnknown')
                                }
                                invalid={!!rowErrors?.premium_share}
                                disabled={isSubmitting}
                              />
                            </Field>
                            <Field
                              id={`vehicle-${index}-deductible`}
                              label={t('insurance.deductible')}
                              error={rowErrors?.deductible}
                            >
                              <NumberInput
                                id={`vehicle-${index}-deductible`}
                                {...registerDecimal(register, `vehicles.${index}.deductible`)}
                                placeholder={t('insuranceForm.deductiblePlaceholder')}
                                invalid={!!rowErrors?.deductible}
                                disabled={isSubmitting}
                              />
                            </Field>
                          </>
                        )}
                      </div>
                      {!isReplace && (
                        <>
                          <Field
                            id={`vehicle-${index}-coverage`}
                            label={t('insurance.coverageLimits')}
                          >
                            <Textarea
                              id={`vehicle-${index}-coverage`}
                              rows={2}
                              {...register(`vehicles.${index}.coverage_limits`)}
                              placeholder={t('insuranceForm.coverageLimitsPlaceholder')}
                              disabled={isSubmitting}
                            />
                          </Field>
                          <NamedFieldsEditor
                            control={control}
                            register={register}
                            name={`vehicles.${index}.fields`}
                            suggestions={SUGGESTED_VEHICLE_FIELDS}
                            disabled={isSubmitting}
                            idPrefix={`vehicle-${index}-field`}
                          />
                          {isEdit && (
                            <Field
                              id={`vehicle-${index}-effective-to`}
                              label={t('insurance.removedOn')}
                              hint={t('insurance.removedOnHint')}
                            >
                              <Input
                                id={`vehicle-${index}-effective-to`}
                                type="date"
                                {...register(`vehicles.${index}.effective_to`)}
                                disabled={isSubmitting}
                              />
                            </Field>
                          )}
                        </>
                      )}
                    </div>
                  )
                })}

                {!isReplace && hasPremium && vehicleRows.length > 0 && (
                  <p
                    role={overAllocated || underAllocated ? 'alert' : undefined}
                    className={`text-sm ${
                      overAllocated || underAllocated ? 'text-danger' : 'text-text-mute'
                    }`}
                  >
                    {overAllocated
                      ? t('insurance.overAllocated', {
                          allocated: money(allocated),
                          premium: money(premium),
                        })
                      : underAllocated
                        ? t('insurance.underAllocated', {
                            allocated: money(allocated),
                            premium: money(premium),
                          })
                        : t('insurance.allocated', {
                            allocated: money(allocated),
                            premium: money(premium),
                          })}
                  </p>
                )}

                {pickable.length > 0 && (
                  <div className="flex gap-2 items-end">
                    <div className="flex-1">
                    <Field id="add-vehicle" label={t('insurance.addVehicle')}>
                      <Select
                        id="add-vehicle"
                        value={pickedVin}
                        onChange={(event) => setPickedVin(event.target.value)}
                        disabled={isSubmitting}
                        placeholder={t('insurance.chooseVehicle')}
                        options={pickable.map((vehicle) => ({
                          value: vehicle.vin,
                          label: vehicleLabel(vehicle),
                        }))}
                      />
                    </Field>
                    </div>
                    <Button
                      type="button"
                      variant="secondary"
                      icon={Plus}
                      onClick={addVehicle}
                      disabled={!pickedVin || isSubmitting}
                    >
                      {t('common:add')}
                    </Button>
                  </div>
                )}
              </>
            )}
          </fieldset>

          <Field id="notes" label={t('common:notes')}>
            <Textarea
              id="notes"
              rows={2}
              {...register('notes')}
              placeholder={t('common:additionalNotes')}
              disabled={isSubmitting}
            />
          </Field>
        </form>
      </FormModalWrapper>

      {showPDFUpload && (
        <InsurancePDFUpload
          onDataExtracted={handlePDFDataExtracted}
          onClose={() => setShowPDFUpload(false)}
        />
      )}
    </>
  )
}
