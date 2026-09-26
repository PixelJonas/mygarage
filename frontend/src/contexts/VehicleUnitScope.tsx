/**
 * The vehicle whose numbers a subtree renders, as far as units go (#172).
 *
 * A vehicle can declare the unit its odometer reads. Inside this scope
 * `useUnitPreference()` lays that unit (distance, and the speed that goes with
 * it) over the account's set, so every component below reads the vehicle's
 * distances in the vehicle's unit without knowing a scope exists. Economy and
 * every rate with a distance underneath stay with the account.
 *
 * `null` means the vehicle follows the account; `undefined` (the default,
 * outside any scope, or an old cached vehicle without the field) means the
 * same. A nested scope wins over an outer one.
 */
import { createContext, useContext, type ReactElement, type ReactNode } from 'react'

export type VehicleDistanceUnit = 'km' | 'mi' | null | undefined

const VehicleUnitScopeContext = createContext<VehicleDistanceUnit>(undefined)

export function VehicleUnitScope({
  distanceUnit,
  children,
}: {
  distanceUnit: VehicleDistanceUnit
  children: ReactNode
}): ReactElement {
  return (
    <VehicleUnitScopeContext.Provider value={distanceUnit}>{children}</VehicleUnitScopeContext.Provider>
  )
}

/** The enclosing vehicle's odometer unit, or undefined outside any vehicle. */
export function useVehicleDistanceUnit(): VehicleDistanceUnit {
  return useContext(VehicleUnitScopeContext)
}
