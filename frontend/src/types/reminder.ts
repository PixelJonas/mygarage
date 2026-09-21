// ============================================================================
// Section A: Generated type aliases from OpenAPI schema
// Source of truth: backend Pydantic models -> openapi.json -> api.generated.ts
// Run `bun run generate:api` after backend schema changes and commit both files.
// ============================================================================

import type { components } from './api.generated'

export type Reminder = components['schemas']['ReminderResponse']
export type ReminderCreate = components['schemas']['ReminderCreate']
export type ReminderUpdate = components['schemas']['ReminderUpdate']
export type RecurrenceSpec = components['schemas']['RecurrenceSpec']
export type AnchorSpec = components['schemas']['AnchorSpec']
export type MaintenanceRuleSummary = components['schemas']['MaintenanceRuleSummary']
export type MaintenanceRuleResponse = components['schemas']['MaintenanceRuleResponse']
export type MaintenanceTypeOption = components['schemas']['MaintenanceTypeResponse']
export type ReminderCompleteRequest = components['schemas']['ReminderCompleteRequest']
export type ReminderCompleteResponse = components['schemas']['ReminderCompleteResponse']
export type ApplyPackPreview = components['schemas']['ApplyPackPreview']
export type PackItemPlan = components['schemas']['PackItemPlan']
export type AnchorChoice = components['schemas']['AnchorChoice']
export type AnchorCandidate = components['schemas']['AnchorCandidate']
export type DuplicateGroup = components['schemas']['DuplicateGroup']
export type ReminderPackSummary = components['schemas']['ReminderPackSummary']
export type ReminderPackDetail = components['schemas']['ReminderPackDetail']
export type ReminderPackItem = components['schemas']['ReminderPackItem']
export type IntervalOverride = components['schemas']['IntervalOverride']
export type SavePackBody = components['schemas']['SaveReminderPackRequest']

// ============================================================================
// Section B: Hand-maintained frontend-only types
// ============================================================================

/** Derived from the ReminderCreate enum — keeps UI dropdowns in sync */
export type ReminderType = NonNullable<ReminderCreate['reminder_type']>

/** Backend uses plain str for status; narrow it for frontend UI logic */
export type ReminderStatus = 'pending' | 'done' | 'dismissed'

/** How a line item's follow-up reminder is shaped in the visit form. */
export type ReminderDraftMode = 'once' | 'recurring'

/**
 * Frontend-only draft used for inline reminder creation on a service line
 * item. `once` is a one-time date reminder; `recurring` carries intervals
 * (canonical km, calendar months, engine hours) that the backend turns into
 * a maintenance rule anchored on THIS visit's date and odometer.
 */
export interface ReminderDraft {
  enabled: boolean
  mode: ReminderDraftMode
  title: string
  due_date?: string
  recurrence: RecurrenceDraft
  notes?: string
}

/** The intervals a recurrence form collects, all optional until validated. */
export interface RecurrenceDraft {
  interval_km?: number
  interval_months?: number
  /** Only packs set days (winterisation, storage checks); an edit keeps them. */
  interval_days?: number
  interval_hours?: number
}

/** The wire payload for a line item's reminder draft. */
export function reminderDraftToCreate(draft: ReminderDraft): ReminderCreate {
  if (draft.mode === 'recurring') {
    return {
      title: draft.title,
      notes: draft.notes,
      recurrence: draft.recurrence,
    }
  }
  return {
    title: draft.title,
    reminder_type: 'date',
    due_date: draft.due_date,
    notes: draft.notes,
  }
}
