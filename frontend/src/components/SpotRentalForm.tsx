import { useTranslation } from 'react-i18next'
import { useMemo, useState, useEffect } from 'react'
import { useForm, type Resolver } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Save } from 'lucide-react'
import FormModalWrapper from './FormModalWrapper'
import { Button, Drawer, Field, Input, Select, Textarea, registerDecimal } from './ui'
import CurrencyInput from './common/CurrencyInput'
import type { SpotRental, SpotRentalCreate, SpotRentalUpdate } from '../types/spotRental'
import type { AddressBookEntry } from '../types/addressBook'
import { makeSpotRentalSchema, type SpotRentalFormData } from '../schemas/spotRental'
import AddressBookAutocomplete from './AddressBookAutocomplete'
import api from '../services/api'
import { useCreateSpotRental, useUpdateSpotRental } from '../hooks/queries/useSpotRentals'
import { toast } from 'sonner'
import { formatDateForInput } from '../utils/dateUtils'
import { applyServerErrors } from '../hooks/useApiFormErrors'
import { getActionErrorMessage } from '../utils/httpErrorHandler'

interface SpotRentalFormProps {
  vin: string
  rental?: SpotRental
  onClose: () => void
  onSuccess: () => void
}

export default function SpotRentalForm({ vin, rental, onClose, onSuccess }: SpotRentalFormProps) {
  const { t } = useTranslation('forms')
  const isEdit = !!rental
  const [error, setError] = useState<string | null>(null)
  const createMutation = useCreateSpotRental(vin)
  const updateMutation = useUpdateSpotRental(vin)
  const [selectedAddressEntry, setSelectedAddressEntry] = useState<AddressBookEntry | null>(null)
  const [showSaveToAddressBook, setShowSaveToAddressBook] = useState(false)
  const [pendingLocationData, setPendingLocationData] = useState<{name: string, address: string} | null>(null)
  const [rateType, setRateType] = useState<'nightly' | 'weekly' | 'monthly'>(() => {
    if (rental?.monthly_rate) return 'monthly'
    if (rental?.weekly_rate) return 'weekly'
    return 'nightly'
  })

  // Zod bakes its messages in at construction, so the schema is rebuilt when
  // the language changes. Only the resolver depends on it — no fetch, no
  // reset() — so a rebuild can't discard what the user typed.
  const schema = useMemo(() => makeSpotRentalSchema(t), [t])

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isSubmitting },
    setError: setFieldError,
  } = useForm<SpotRentalFormData>({
    resolver: zodResolver(schema) as Resolver<SpotRentalFormData>,
    defaultValues: {
      location_name: rental?.location_name || '',
      location_address: rental?.location_address || '',
      check_in_date: formatDateForInput(rental?.check_in_date),
      check_out_date: rental?.check_out_date ? formatDateForInput(rental.check_out_date) : '',
      nightly_rate: rental?.nightly_rate != null ? Number(rental.nightly_rate) : undefined,
      weekly_rate: rental?.weekly_rate != null ? Number(rental.weekly_rate) : undefined,
      monthly_rate: rental?.monthly_rate != null ? Number(rental.monthly_rate) : undefined,
      electric: rental?.electric != null ? Number(rental.electric) : undefined,
      water: rental?.water != null ? Number(rental.water) : undefined,
      waste: rental?.waste != null ? Number(rental.waste) : undefined,
      total_cost: rental?.total_cost != null ? Number(rental.total_cost) : undefined,
      amenities: rental?.amenities || '',
      notes: rental?.notes || '',
    },
  })

  // Auto-calculate total cost from rate + utilities
  const nightlyRate = watch('nightly_rate')
  const weeklyRate = watch('weekly_rate')
  const monthlyRate = watch('monthly_rate')
  const electric = watch('electric')
  const water = watch('water')
  const waste = watch('waste')

  useEffect(() => {
    // Convert all values to numbers, handling both string and number inputs
    const toNumber = (val: number | string | undefined): number => {
      if (!val) return 0
      const num = typeof val === 'string' ? parseFloat(val) : val
      return isNaN(num) ? 0 : num
    }

    let baseRate = 0

    if (rateType === 'nightly' && nightlyRate) {
      baseRate = toNumber(nightlyRate)
    } else if (rateType === 'weekly' && weeklyRate) {
      baseRate = toNumber(weeklyRate)
    } else if (rateType === 'monthly' && monthlyRate) {
      baseRate = toNumber(monthlyRate)
    }

    const elec = toNumber(electric)
    const wat = toNumber(water)
    const wst = toNumber(waste)
    const calculatedTotal = baseRate + elec + wat + wst

    if (calculatedTotal > 0) {
      setValue('total_cost', parseFloat(calculatedTotal.toFixed(2)))
    }
  }, [rateType, nightlyRate, weeklyRate, monthlyRate, electric, water, waste, setValue])

  const handleAddressBookSelect = (entry: AddressBookEntry | null) => {
    setSelectedAddressEntry(entry)
    if (entry) {
      // Auto-fill address from selected entry
      const fullAddress = [
        entry.address,
        entry.city,
        entry.state,
        entry.zip_code
      ].filter(Boolean).join(', ')

      setValue('location_address', fullAddress)
    }
  }

  const handleSaveToAddressBook = async () => {
    if (!pendingLocationData) return

    try {
      await api.post('/address-book', {
        business_name: pendingLocationData.name,
        address: pendingLocationData.address,
        category: 'RV Park'
      })
      toast.success(t('spotRental.locationSaved'))
    } catch {
      toast.error(t('spotRental.failedToSaveLocation'))
    } finally {
      setShowSaveToAddressBook(false)
      setPendingLocationData(null)
      onSuccess()
      onClose()
    }
  }

  // The save already succeeded before the prompt shows; "Skip" is the No path.
  // The nested Drawer routes its Esc / close button / backdrop click here.
  const skipSaveToAddressBook = () => {
    setShowSaveToAddressBook(false)
    setPendingLocationData(null)
    onSuccess()
    onClose()
  }

  const onSubmit = async (data: SpotRentalFormData) => {
    setError(null)

    try {
      // Zod has already parsed and validated all numeric fields - no parseFloat needed!
      const payload: SpotRentalCreate | SpotRentalUpdate = {
        location_name: data.location_name || undefined,
        location_address: data.location_address || undefined,
        check_in_date: data.check_in_date,
        check_out_date: data.check_out_date || undefined,
        nightly_rate: data.nightly_rate,
        weekly_rate: data.weekly_rate,
        monthly_rate: data.monthly_rate,
        electric: data.electric,
        water: data.water,
        waste: data.waste,
        total_cost: data.total_cost,
        amenities: data.amenities || undefined,
        notes: data.notes || undefined,
      }

      if (isEdit) {
        await updateMutation.mutateAsync({ id: rental.id, ...payload })
        onSuccess()
        onClose()
      } else {
        await createMutation.mutateAsync(payload as SpotRentalCreate)

        // Check if this is a new location (not from address book)
        if (data.location_name && !selectedAddressEntry) {
          setPendingLocationData({
            name: data.location_name,
            address: data.location_address || ''
          })
          setShowSaveToAddressBook(true)
        } else {
          onSuccess()
          onClose()
        }
      }
    } catch (err) {
      // attached.length === 0 catches a non-422 failure (network drop, 500):
      // it carries no field problems at all, so `unhandled` alone would stay
      // empty and this banner would never show.
      const { attached, unhandled } = applyServerErrors<SpotRentalFormData>(setFieldError, err, [
        'location_name',
        'location_address',
        'check_in_date',
        'check_out_date',
        'nightly_rate',
        'weekly_rate',
        'monthly_rate',
        'electric',
        'water',
        'waste',
        'total_cost',
        'amenities',
        'notes',
      ])
      if (attached.length === 0 || unhandled.length > 0) {
        setError(getActionErrorMessage(err, t('spotRental.saveAction')))
      }
    }
  }

  return (
    <>
    <FormModalWrapper
      title={isEdit ? t('spotRental.editTitle') : t('spotRental.createTitle')}
      onClose={onClose}
      width="md"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
            {t('common:cancel')}
          </Button>
          <Button type="submit" form="spot-rental-form" variant="primary" icon={Save} loading={isSubmitting} disabled={isSubmitting}>
            {isSubmitting ? t('common:saving') : isEdit ? t('common:update') : t('common:create')}
          </Button>
        </>
      }
    >
        <form id="spot-rental-form" onSubmit={handleSubmit(onSubmit as Parameters<typeof handleSubmit>[0])} className="p-6 space-y-4">
          {error && (
            <div className="bg-danger/10 border border-danger rounded-lg p-3">
              <p className="text-sm text-danger">{error}</p>
            </div>
          )}

          <Field id="location_name" label={t('spotRental.locationName')} hint={t('spotRental.addressBookHint')} error={errors.location_name}>
            <AddressBookAutocomplete
              id="location_name"
              value={watch('location_name') || ''}
              onChange={(value) => {
                setValue('location_name', value)
                if (!value) {
                  setSelectedAddressEntry(null)
                }
              }}
              onSelectEntry={handleAddressBookSelect}
              placeholder={t('spotRentalForm.locationNamePlaceholder')}
              className={`ui-focus-input ui-motion w-full rounded-control border bg-surface-2 px-3 py-2 text-sm text-text ${
                errors.location_name ? 'border-danger' : 'border-border'
              }`}
            />
          </Field>

          <Field id="location_address" label={t('spotRental.address')} error={errors.location_address}>
            <Textarea
              id="location_address"
              rows={2}
              {...register('location_address')}
              placeholder={t('spotRental.addressPlaceholder')}
              invalid={!!errors.location_address}
              disabled={isSubmitting}
            />
          </Field>

          <div className="grid grid-cols-2 gap-4">
            <Field id="check_in_date" label={t('spotRental.checkInDate')} required error={errors.check_in_date}>
              <Input id="check_in_date" type="date" {...register('check_in_date')} invalid={!!errors.check_in_date} disabled={isSubmitting} />
            </Field>

            <Field id="check_out_date" label={t('spotRental.checkOutDate')} hint={t('spotRental.leaveBlankHint')} error={errors.check_out_date}>
              <Input id="check_out_date" type="date" {...register('check_out_date')} invalid={!!errors.check_out_date} disabled={isSubmitting} />
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Field id="rate_type" label={t('spotRental.rateType')}>
              <Select
                id="rate_type"
                value={rateType}
                onChange={(e) => {
                  const newType = e.target.value as 'nightly' | 'weekly' | 'monthly'
                  setRateType(newType)
                  if (newType === 'nightly') {
                    setValue('weekly_rate', undefined)
                    setValue('monthly_rate', undefined)
                  } else if (newType === 'weekly') {
                    setValue('nightly_rate', undefined)
                    setValue('monthly_rate', undefined)
                  } else {
                    setValue('nightly_rate', undefined)
                    setValue('weekly_rate', undefined)
                  }
                }}
                disabled={isSubmitting}
                options={[
                  { value: 'nightly', label: t('spotRental.nightly') },
                  { value: 'weekly', label: t('spotRental.weekly') },
                  { value: 'monthly', label: t('spotRental.monthly') },
                ]}
              />
            </Field>

            <Field
              id="rate_amount"
              label={t(
                rateType === 'nightly'
                  ? 'spotRentalForm.nightlyRate'
                  : rateType === 'weekly'
                    ? 'spotRentalForm.weeklyRate'
                    : 'spotRentalForm.monthlyRate'
              )}
              error={rateType === 'nightly' ? errors.nightly_rate : rateType === 'weekly' ? errors.weekly_rate : errors.monthly_rate}
            >
              <CurrencyInput
                id="rate_amount"
                {...registerDecimal(register, rateType === 'nightly' ? 'nightly_rate' : rateType === 'weekly' ? 'weekly_rate' : 'monthly_rate')}
                placeholder={rateType === 'nightly' ? '45.00' : rateType === 'weekly' ? '280.00' : '950.00'}
                invalid={
                  !!(
                    (rateType === 'nightly' && errors.nightly_rate) ||
                    (rateType === 'weekly' && errors.weekly_rate) ||
                    (rateType === 'monthly' && errors.monthly_rate)
                  )
                }
                disabled={isSubmitting}
              />
            </Field>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <Field id="electric" label={t('spotRental.electric')} error={errors.electric}>
              <CurrencyInput
                id="electric"
                {...registerDecimal(register, 'electric')}
                placeholder="50.00"
                invalid={!!errors.electric}
                disabled={isSubmitting}
              />
            </Field>

            <Field id="water" label={t('spotRental.water')} error={errors.water}>
              <CurrencyInput
                id="water"
                {...registerDecimal(register, 'water')}
                placeholder="30.00"
                invalid={!!errors.water}
                disabled={isSubmitting}
              />
            </Field>

            <Field id="waste" label={t('spotRental.waste')} error={errors.waste}>
              <CurrencyInput
                id="waste"
                {...registerDecimal(register, 'waste')}
                placeholder="20.00"
                invalid={!!errors.waste}
                disabled={isSubmitting}
              />
            </Field>
          </div>

          <Field id="total_cost" label={t('common:totalCost')} hint={t('spotRental.autoCalculatedHint')} error={errors.total_cost}>
            <CurrencyInput
              id="total_cost"
              {...registerDecimal(register, 'total_cost')}
              placeholder={t('spotRentalForm.autoCalculatedPlaceholder')}
              readOnly
            />
          </Field>

          <Field id="amenities" label={t('spotRental.amenities')} error={errors.amenities}>
            <Textarea
              id="amenities"
              rows={2}
              {...register('amenities')}
              placeholder={t('spotRentalForm.amenitiesPlaceholder')}
              invalid={!!errors.amenities}
              disabled={isSubmitting}
            />
          </Field>

          <Field id="notes" label={t('common:notes')} error={errors.notes}>
            <Textarea
              id="notes"
              rows={3}
              {...register('notes')}
              placeholder={t('spotRental.notesPlaceholder')}
              invalid={!!errors.notes}
              disabled={isSubmitting}
            />
          </Field>
        </form>
    </FormModalWrapper>

      {/* Save to Address Book — nested drawer above the parent (+10). Esc /
         close / backdrop all route to skipSaveToAddressBook (the "No" path). */}
      <Drawer
        open={showSaveToAddressBook && !!pendingLocationData}
        nested
        onClose={skipSaveToAddressBook}
        title={t('spotRental.saveToAddressBook')}
        width="2xs"
        closeLabel={t('common:close')}
        footer={
          <>
            <Button variant="secondary" onClick={skipSaveToAddressBook}>
              {t('spotRental.noSkip')}
            </Button>
            <Button variant="primary" onClick={handleSaveToAddressBook}>
              {t('spotRental.yesSave')}
            </Button>
          </>
        }
      >
        <p className="text-sm text-text-mute">
          {t('spotRental.saveToAddressBookPrompt', { name: pendingLocationData?.name ?? '' })}
        </p>
      </Drawer>
    </>
  )
}
