// ============================================================================
// Section A: Generated type aliases from OpenAPI schema
// Source of truth: backend Pydantic models -> openapi.json -> api.generated.ts
// Run `bun run generate:api` after backend schema changes and commit both files.
// ============================================================================

import type { components } from './api.generated'

export type FinancingRecord = components['schemas']['FinancingRecordResponse']
export type FinancingRecordCreate = components['schemas']['FinancingRecordCreate']
export type FinancingRecordUpdate = components['schemas']['FinancingRecordUpdate']
export type FinancingRecordListResponse = components['schemas']['FinancingRecordListResponse']

// ============================================================================
// Section B: Hand-maintained frontend-only types
// ============================================================================

// Backend uses Literal["lease_payment", "loan_payment", "upfront_fee"]
// which generates the correct union — re-export for convenience.
export type FinancingCategory = FinancingRecord['category']
