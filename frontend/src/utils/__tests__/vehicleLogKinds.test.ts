/**
 * Which records a vehicle can log. The vehicle page's tabs and Quick Entry's
 * buttons both read these, so a fifth wheel offers propane in both places and
 * mileage in neither.
 */
import { describe, it, expect } from 'vitest'
import { fillUpKind, vehicleLogKinds } from '../vehicleLogKinds'

describe('vehicleLogKinds', () => {
  it('gives a fifth wheel propane, and no fuel, DEF or odometer', () => {
    expect(vehicleLogKinds({ vehicle_type: 'FifthWheel', usage_unit: 'distance' })).toEqual({
      motorized: false,
      fuel: false,
      propane: true,
      def: false,
      defHistory: false,
      odometer: false,
      hours: false,
    })
  })

  it.each(['Trailer', 'TravelTrailer'])('gives a %s no odometer, even when it tracks distance', (type) => {
    const kinds = vehicleLogKinds({ vehicle_type: type, usage_unit: 'distance' })

    expect(kinds.odometer).toBe(false)
    expect(kinds.fuel).toBe(false)
  })

  it('gives a motorhome fuel, propane and an odometer', () => {
    const kinds = vehicleLogKinds({ vehicle_type: 'RV', fuel_type: 'gasoline' })

    expect([kinds.fuel, kinds.propane, kinds.odometer, kinds.def]).toEqual([true, true, true, false])
  })

  it('lets a diesel log DEF, on either fuel slot', () => {
    const diesel = vehicleLogKinds({ vehicle_type: 'Truck', fuel_type: 'diesel' })
    // With no DEF tank size set, the DEF tab still shows.
    expect([diesel.def, diesel.defHistory]).toEqual([true, true])
    expect(
      vehicleLogKinds({ vehicle_type: 'Truck', fuel_type: 'gasoline', fuel_type_secondary: 'diesel' }).def,
    ).toBe(true)
    expect(vehicleLogKinds({ vehicle_type: 'Truck', fuel_type: 'gasoline' }).def).toBe(false)
  })

  it('shows, but cannot add to, the DEF history of a vehicle that is no longer diesel', () => {
    // The API refuses a DEF record unless a fuel slot is diesel.
    const kinds = vehicleLogKinds({ vehicle_type: 'Car', fuel_type: 'gasoline', def_tank_capacity_liters: '18.9' })

    expect([kinds.defHistory, kinds.def]).toEqual([true, false])
  })

  it('gives an hours-only machine hours, not an odometer', () => {
    const kinds = vehicleLogKinds({ vehicle_type: 'Tractor', usage_unit: 'hours' })

    expect([kinds.hours, kinds.odometer]).toEqual([true, false])
  })

  it('gives a bicycle an odometer and no fuel', () => {
    const kinds = vehicleLogKinds({ vehicle_type: 'Bicycle' })

    expect([kinds.odometer, kinds.fuel]).toEqual([true, false])
  })

  it('offers nothing before the vehicle is known', () => {
    expect(Object.values(vehicleLogKinds(null)).some(Boolean)).toBe(false)
  })
})

describe('fillUpKind', () => {
  it.each([
    [{ fuel: true, def: true, propane: true }, 'fuel'],
    [{ fuel: false, def: true, propane: true }, 'def'],
    [{ fuel: false, def: false, propane: true }, 'propane'],
    [{ fuel: false, def: false, propane: false }, null],
  ] as const)('reads "add fuel" as the first fill-up the vehicle has', (kinds, expected) => {
    expect(fillUpKind(kinds)).toBe(expected)
  })
})
