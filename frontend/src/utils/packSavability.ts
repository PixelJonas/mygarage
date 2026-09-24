/**
 * Which of a vehicle's rules can go in a saved pack.
 *
 * Two rules, and both come from the same place: the backend resolves a pack item
 * to a rule by `maintenance_type`, so a pack cannot express anything that does
 * not survive being keyed that way.
 *
 * - A TYPELESS rule would come back typed when the pack is applied, and start
 *   matching services by type, which is the opposite of what a typeless rule
 *   means.
 * - TWO SELECTED rules of one type would resolve to the same rule and the second
 *   would silently vanish.
 *
 * This duplicates `reminder_pack_service.unsavable_reason`, deliberately and
 * narrowly, so the dialog can grey a row out with its reason instead of letting
 * the user submit and read a 422. `__tests__/packSavability.test.ts` pins the
 * same matrix the backend's own unit test pins, so the two cannot drift quietly.
 * The API is still the authority: it refuses either case whatever the UI allows.
 */

import type { MaintenanceRuleResponse } from '../types/reminder'

export type UnsavableReason = 'typeless' | 'repeatedType'

/**
 * The maintenance types more than one of these rules carries.
 *
 * Computed over the CHECKED rules, not the whole vehicle, because the backend
 * computes it over the selection: picking one of two same-type rules is a
 * perfectly good pack, so unticking one must clear the other's warning.
 */
export function repeatedTypes(rules: MaintenanceRuleResponse[]): Set<string> {
  const seen = new Set<string>()
  const repeated = new Set<string>()
  for (const rule of rules) {
    const type = rule.maintenance_type
    if (!type) continue
    if (seen.has(type)) repeated.add(type)
    seen.add(type)
  }
  return repeated
}

/**
 * A sensible opening selection: everything savable, with later duplicates of a
 * type and typeless rules left out.
 *
 * Ticking everything by default would open the dialog in a state the API
 * refuses whenever a vehicle has two rules of a type, so the default has to skip
 * those rather than the user having to work out which two are fighting.
 */
export function defaultSelection(rules: MaintenanceRuleResponse[]): Set<number> {
  const chosen = new Set<number>()
  const takenTypes = new Set<string>()
  for (const rule of rules) {
    const type = rule.maintenance_type
    if (!type || takenTypes.has(type)) continue
    takenTypes.add(type)
    chosen.add(rule.id)
  }
  return chosen
}

/** Why this rule cannot go in a pack, or null when it can. */
export function unsavableReason(
  rule: MaintenanceRuleResponse,
  repeated: Set<string>
): UnsavableReason | null {
  if (!rule.maintenance_type) return 'typeless'
  if (repeated.has(rule.maintenance_type)) return 'repeatedType'
  return null
}
