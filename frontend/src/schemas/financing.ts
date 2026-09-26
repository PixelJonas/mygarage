import { z } from 'zod'
import type { TFunction } from 'i18next'
import { makeDateSchema, makeCurrencySchema, makeNotesSchema } from './shared'

/** Financing record schema matching backend/app/schemas/financing.py. */

/** Persisted category values; never translate these. */
export const FINANCING_CATEGORY_VALUES = ['lease_payment', 'loan_payment', 'upfront_fee'] as const

export type FinancingCategoryValue = (typeof FINANCING_CATEGORY_VALUES)[number]

export const FINANCING_CATEGORIES = [
  { value: 'lease_payment', labelKey: 'forms:financingCategories.leasePayment' },
  { value: 'loan_payment', labelKey: 'forms:financingCategories.loanPayment' },
  { value: 'upfront_fee', labelKey: 'forms:financingCategories.upfrontFee' },
] as const satisfies readonly { value: FinancingCategoryValue; labelKey: string }[]

export const makeFinancingRecordSchema = (t: TFunction) =>
  z.object({
    date: makeDateSchema(t),
    category: z.enum(FINANCING_CATEGORY_VALUES, {
      message: t('common:validation.financing.categoryRequired'),
    }),
    amount: makeCurrencySchema(t),
    vendor_id: z.number().optional(),
    notes: makeNotesSchema(t).optional(),
  })

// Use z.output for Zod v4 compatibility with z.coerce fields
export type FinancingRecordInput = z.input<ReturnType<typeof makeFinancingRecordSchema>>
export type FinancingRecordFormData = z.output<ReturnType<typeof makeFinancingRecordSchema>>
