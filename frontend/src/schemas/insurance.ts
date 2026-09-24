import { z } from 'zod'
import type { TFunction } from 'i18next'
import { makeNumericField } from './shared'

/**
 * Insurance policy schema matching backend Pydantic validators.
 * See: backend/app/schemas/insurance.py
 */

/**
 * Option lists for the insurance form.
 *
 * `value` is the persisted/API value — it must never be translated or changed.
 * `labelKey` is the i18n key for the human-readable label, resolved at render.
 */
export const POLICY_TYPES = [
  { value: 'Liability', labelKey: 'forms:policyTypes.liability' },
  { value: 'Comprehensive', labelKey: 'forms:policyTypes.comprehensive' },
  { value: 'Collision', labelKey: 'forms:policyTypes.collision' },
  { value: 'Full Coverage', labelKey: 'forms:policyTypes.fullCoverage' },
  { value: 'Minimum', labelKey: 'forms:policyTypes.minimum' },
  { value: 'Other', labelKey: 'forms:policyTypes.other' },
] as const

export const PREMIUM_FREQUENCIES = [
  { value: 'Monthly', labelKey: 'forms:premiumFrequencies.monthly' },
  { value: 'Quarterly', labelKey: 'forms:premiumFrequencies.quarterly' },
  { value: 'Semi-Annual', labelKey: 'forms:premiumFrequencies.semiAnnual' },
  { value: 'Annual', labelKey: 'forms:premiumFrequencies.annual' },
] as const

/**
 * Factory, not a module-level constant — see the header of schemas/auth.ts for
 * why. `premium_amount` and `deductible` are genuinely optional on the backend
 * (`Decimal | None`); the bug (#140) was that the form sent the raw string
 * `"528,25"` for a comma-decimal locale and `""` for an untouched optional
 * field, both of which the backend's 422 rejected with no per-field detail.
 * Routing them through the locale-aware `NumberInput`/`registerDecimal` fixes
 * both — it reports `common:validation.amount.invalid` instead of a bare
 * status code.
 *
 * NOT `makeOptionalCurrencySchema` though: that factory's 99,999.99 ceiling
 * doesn't exist on the backend (`insurance.py` — `ge=0`, no `le`), and
 * insurance is THE #140 form, so a client-side cap here would reject
 * legitimate values (a high-value collector-car policy, a commercial umbrella
 * premium) the API accepts. Bespoke min:0/max:Infinity via the exported
 * `makeNumericField`, same technique as `warranty.mileage_limit_km`.
 */
/** Labels offered as one-tap chips in the named-fields editor. Suggestions
 *  only: the stored label is whatever text the user keeps, so these are
 *  translated for display and never persisted as keys. */
export const SUGGESTED_POLICY_FIELDS = [
  'forms:insuranceFieldLabels.agentName',
  'forms:insuranceFieldLabels.agentPhone',
  'forms:insuranceFieldLabels.claimsPhone',
] as const

/** Deliberately none of the standard coverages: those have their own inputs
 *  in the coverage editor now, and offering them here as free text would give
 *  a vehicle two places to hold its collision deductible. */
export const SUGGESTED_VEHICLE_FIELDS = [
  'forms:insuranceFieldLabels.lienholder',
  'forms:insuranceFieldLabels.garagingAddress',
  'forms:insuranceFieldLabels.discounts',
] as const

const amountField = (t: TFunction) =>
  makeNumericField(t, {
    min: 0,
    max: Infinity,
    negativeKey: 'common:validation.amount.negative',
    tooLargeKey: 'common:validation.amount.tooLarge',
    invalidKey: 'common:validation.amount.invalid',
  })

const namedFieldSchema = (t: TFunction) =>
  z.object({
    label: z.string().trim().min(1, t('common:required')).max(60),
    value: z.string().trim().min(1, t('common:required')).max(255),
  })

/** One row of the standard coverage checklist.
 *
 *  The form carries EVERY catalogue coverage, included or not, so the checklist
 *  maps one-to-one onto stable array indices; `PolicyForm` drops the unticked
 *  ones on submit. A coverage the catalogue gives no such slot keeps
 *  `undefined` there and is stripped the same way, because the API rejects an
 *  amount it has nowhere to show. */
const coverageSchema = (t: TFunction) =>
  z.object({
    coverage_key: z.string().min(1),
    included: z.boolean(),
    limit_primary: amountField(t),
    limit_secondary: amountField(t),
    deductible: amountField(t),
    premium: amountField(t),
  })

const policyVehicleSchema = (t: TFunction) =>
  z.object({
    vin: z.string().min(1),
    policy_type: z.string().min(1, t('common:validation.policyType.required')),
    premium_share: amountField(t),
    deductible: amountField(t),
    notes: z.string().optional(),
    effective_to: z.string().optional(),
    coverages: z.array(coverageSchema(t)),
    fields: z.array(namedFieldSchema(t)),
  })

export const makeInsuranceSchema = (t: TFunction) =>
  z
    .object({
      provider: z.string().min(1, t('common:validation.provider.required')),
      policy_number: z.string().min(1, t('common:validation.policyNumber.required')),
      start_date: z.string().min(1, t('common:validation.date.required')),
      end_date: z.string().min(1, t('common:validation.date.required')),
      premium_amount: amountField(t),
      premium_frequency: z.string().optional(),
      notes: z.string().optional(),
      fields: z.array(namedFieldSchema(t)),
      vehicles: z.array(policyVehicleSchema(t)),
    })
    .refine((data) => !data.start_date || !data.end_date || data.end_date >= data.start_date, {
      path: ['end_date'],
      message: t('forms:insurance.endBeforeStart'),
    })

// Amounts are `unknown` going in (raw NumberInput text or a number from
// defaultValues) and `number | undefined` coming out: the resolver is cast to
// the output type at the call site, like the sibling record forms built on
// the same shared.ts factories.
export type InsuranceFormData = z.output<ReturnType<typeof makeInsuranceSchema>>
export type PolicyVehicleFormData = InsuranceFormData['vehicles'][number]
export type CoverageFormData = PolicyVehicleFormData['coverages'][number]

/** `currentEnd` is the term being renewed: the next one may not start before
 *  it ends, or both would be active at once and both premiums would accrue. */
export const makeRenewSchema = (t: TFunction, currentEnd: string) =>
  z
    .object({
      start_date: z.string().min(1, t('common:validation.date.required')),
      end_date: z.string().min(1, t('common:validation.date.required')),
      premium_amount: amountField(t),
    })
    .refine((data) => data.end_date >= data.start_date, {
      path: ['end_date'],
      message: t('forms:insurance.endBeforeStart'),
    })
    .refine((data) => !data.start_date || data.start_date >= currentEnd, {
      path: ['start_date'],
      message: t('forms:insurance.renewOverlaps'),
    })

export type RenewFormData = z.output<ReturnType<typeof makeRenewSchema>>
