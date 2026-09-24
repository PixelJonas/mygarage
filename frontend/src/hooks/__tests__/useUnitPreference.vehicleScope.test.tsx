/**
 * A vehicle's odometer unit, laid over the account's set inside a
 * `VehicleUnitScope` (#172). Only `AuthContext` is mocked, so the REAL
 * `useUnitPreference` runs: the 73 test files that mock that hook prove
 * nothing about the scope.
 */
import { describe, it, expect, vi } from 'vitest'
import type { ReactNode } from 'react'
import { renderHook } from '@testing-library/react'
import { METRIC_UNITS, makeUnitSet, type User } from '@/__tests__/factories'

const h = vi.hoisted(() => ({ user: null as Partial<User> | null }))
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: h.user, isAuthenticated: h.user !== null, defaultUnitPrefs: null }),
}))

import { VehicleUnitScope, type VehicleDistanceUnit } from '../../contexts/VehicleUnitScope'
import { useAccountUnitPreference, useUnitPreference } from '../useUnitPreference'
import { useUnitFormat, useUnitFormatFor } from '../useUnitFormat'
import { unitsForVehicle } from '../../types/units'

const scope = (distanceUnit: VehicleDistanceUnit) =>
  function Wrapper({ children }: { children: ReactNode }) {
    return <VehicleUnitScope distanceUnit={distanceUnit}>{children}</VehicleUnitScope>
  }

describe('unitsForVehicle', () => {
  it('returns the same object when the vehicle follows the account', () => {
    expect(unitsForVehicle(METRIC_UNITS, null)).toBe(METRIC_UNITS)
    expect(unitsForVehicle(METRIC_UNITS, undefined)).toBe(METRIC_UNITS)
    expect(unitsForVehicle(METRIC_UNITS, 'miles')).toBe(METRIC_UNITS)
  })

  it('sets distance and speed and nothing else', () => {
    expect(unitsForVehicle(METRIC_UNITS, 'mi')).toEqual({ ...METRIC_UNITS, distance: 'mi', speed: 'mph' })
  })

  it('overrides a mismatched account on both fields', () => {
    const odd = makeUnitSet({ distance: 'km', speed: 'mph' })
    expect(unitsForVehicle(odd, 'km')).toEqual({ ...odd, speed: 'kmh' })
  })
})

describe('useUnitPreference in a vehicle scope', () => {
  it('lays the vehicle over a km account', () => {
    h.user = { unit_preference: 'metric', resolved_units: METRIC_UNITS }
    const { result } = renderHook(() => useUnitPreference(), { wrapper: scope('mi') })
    const { units } = result.current
    expect([units.distance, units.speed, units.volume]).toEqual(['mi', 'mph', 'L'])
    expect(result.current.system).toBe('metric') // still collapsed from volume
  })

  it('is the account outside any scope, and keeps its identity', () => {
    h.user = { unit_preference: 'metric', resolved_units: METRIC_UNITS }
    const { result, rerender } = renderHook(() => useUnitPreference())
    const first = result.current.units
    rerender()
    expect(result.current.units).toBe(first)
    expect(first.distance).toBe('km')
  })

  it('keeps the scoped set stable across renders', () => {
    h.user = { unit_preference: 'metric', resolved_units: METRIC_UNITS }
    const { result, rerender } = renderHook(() => useUnitPreference(), { wrapper: scope('mi') })
    const first = result.current.units
    rerender()
    expect(result.current.units).toBe(first)
  })

  it('the account hook ignores the scope', () => {
    h.user = { unit_preference: 'metric', resolved_units: METRIC_UNITS }
    const { result } = renderHook(() => useAccountUnitPreference(), { wrapper: scope('mi') })
    expect(result.current.units.distance).toBe('km')
  })
})

describe('show-both inside a scope', () => {
  it('pairs the vehicle unit with its counterpart, not the account unit', () => {
    h.user = { unit_preference: 'metric', show_both_units: true, resolved_units: METRIC_UNITS }
    const { result } = renderHook(() => useUnitFormat(), { wrapper: scope('mi') })
    const text = result.current.distance.format(16093.44)
    expect(text.indexOf('mi')).toBeGreaterThanOrEqual(0)
    expect(text.indexOf('mi')).toBeLessThan(text.indexOf('km')) // "10,000 mi (16,093 km)"
  })
})

describe('useUnitFormatFor', () => {
  it('formats one row per vehicle on a mixed page', () => {
    h.user = { unit_preference: 'metric', resolved_units: METRIC_UNITS }
    const { result } = renderHook(() => useUnitFormatFor())
    expect(result.current('mi').distance.label).toBe('mi')
    expect(result.current(null).distance.label).toBe('km')
    expect(result.current('mi')).toBe(result.current('mi'))
  })
})
