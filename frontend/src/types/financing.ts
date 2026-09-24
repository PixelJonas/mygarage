import type { components } from './api.generated'

export type FinancingRecord = components['schemas']['FinancingRecordResponse']
export type FinancingRecordCreate = components['schemas']['FinancingRecordCreate']
export type FinancingRecordUpdate = components['schemas']['FinancingRecordUpdate']
export type FinancingRecordListResponse = components['schemas']['FinancingRecordListResponse']

export type FinancingCategory = FinancingRecord['category']
