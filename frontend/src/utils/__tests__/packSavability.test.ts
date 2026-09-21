import { describe, it, expect } from 'vitest'
import { defaultSelection, repeatedTypes, unsavableReason } from '../packSavability'
import type { MaintenanceRuleResponse } from '../../types/reminder'

/**
 * This mirrors `tests/unit/services/test_saved_pack_policy.py::TestWhatAPackMayContain`.
 *
 * The rules are duplicated on purpose: the dialog has to grey a row out with its
 * reason rather than letting the user submit and read a 422. Duplicated logic can
 * drift, so the same matrix is asserted on both sides, and the API stays the
 * authority either way.
 */

const rule = (id: number, type: string | null, title = `Rule ${id}`): MaintenanceRuleResponse =>
  ({
    id,
    maintenance_type: type,
    title,
    is_active: true,
    interval_months: 6,
  }) as MaintenanceRuleResponse

describe('what a pack may contain', () => {
  it('refuses a typeless rule', () => {
    expect(unsavableReason(rule(1, null), new Set())).toBe('typeless')
  })

  it('refuses a rule whose type another selected rule already covers', () => {
    expect(unsavableReason(rule(1, 'engine_oil_filter'), new Set(['engine_oil_filter']))).toBe(
      'repeatedType'
    )
  })

  it('accepts an ordinary typed rule', () => {
    expect(unsavableReason(rule(1, 'engine_oil_filter'), new Set())).toBeNull()
  })
})

describe('finding the conflicts', () => {
  it('names only the types carried more than once', () => {
    const rules = [
      rule(1, 'engine_oil_filter'),
      rule(2, 'engine_oil_filter'),
      rule(3, 'tire_rotation'),
    ]
    expect([...repeatedTypes(rules)]).toEqual(['engine_oil_filter'])
  })

  it('never treats two typeless rules as a repeated type', () => {
    // They are refused for being typeless, which names the real problem. Calling
    // them a clash would send the user hunting for a duplicate that isn't there.
    expect([...repeatedTypes([rule(1, null), rule(2, null)])]).toEqual([])
  })

  it('is computed over the selection, so unticking one clears the other', () => {
    const rules = [rule(1, 'engine_oil_filter'), rule(2, 'engine_oil_filter')]
    expect(repeatedTypes(rules).size).toBe(1)
    expect(repeatedTypes(rules.slice(0, 1)).size).toBe(0)
  })
})

describe('the opening selection', () => {
  it('ticks everything savable', () => {
    const rules = [rule(1, 'engine_oil_filter'), rule(2, 'tire_rotation')]
    expect([...defaultSelection(rules)]).toEqual([1, 2])
  })

  it('leaves out the later duplicate of a type', () => {
    // Ticking both would open the dialog in a state the API refuses, and leave
    // the user to work out which two rows are fighting.
    const rules = [rule(1, 'engine_oil_filter'), rule(2, 'engine_oil_filter')]
    expect([...defaultSelection(rules)]).toEqual([1])
  })

  it('leaves out a typeless rule', () => {
    const rules = [rule(1, null), rule(2, 'tire_rotation')]
    expect([...defaultSelection(rules)]).toEqual([2])
  })

  it('never opens in a state the API would refuse', () => {
    // The property behind the three cases above, which is what actually matters.
    const rules = [
      rule(1, 'engine_oil_filter'),
      rule(2, 'engine_oil_filter'),
      rule(3, null),
      rule(4, 'tire_rotation'),
      rule(5, null),
    ]
    const selected = rules.filter((r) => defaultSelection(rules).has(r.id))
    const conflicts = repeatedTypes(selected)
    expect(selected.filter((r) => unsavableReason(r, conflicts) !== null)).toEqual([])
  })
})
