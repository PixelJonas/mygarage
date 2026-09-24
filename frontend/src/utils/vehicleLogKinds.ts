/**
 * Which records a vehicle can log, from its type, fuel and usage settings.
 *
 * ★ ONE RULE, TWO SURFACES. The vehicle page's tabs and Quick Entry's buttons
 * both read this. Quick Entry used to keep its own list, which offered every
 * vehicle Fuel Up and Mileage: a fifth wheel got the engine fuel form, never
 * its propane, and an odometer it does not have.
 *
 * Pure: structural input, so a full vehicle and Quick Entry's slim row both
 * pass.
 */

import { isDieselFuelType } from '../constants/fuel'
import { NON_MOTORIZED_TYPES, NO_FUEL_TYPES } from '../schemas/vehicle'
import { getUsageTracking } from './usageTracking'

interface VehicleLogSource {
  vehicle_type?: string | null
  fuel_type?: string | null
  fuel_type_secondary?: string | null
  def_tank_capacity_liters?: number | string | null
  usage_unit?: string | null
  secondary_usage_enabled?: boolean | null
}

export interface VehicleLogKinds {
  /** Not a trailer: it has a drivetrain, tires and an odometer. */
  motorized: boolean
  /** Fuel (or charge) fill-ups. */
  fuel: boolean
  /** Propane fills: the living-quarters types. */
  propane: boolean
  /** New DEF top-ups: a diesel in either fuel slot, which is what the API accepts. */
  def: boolean
  /** DEF records shown, read-only once the vehicle is no longer diesel. */
  defHistory: boolean
  odometer: boolean
  hours: boolean
}

const PROPANE_TYPES: readonly string[] = ['RV', 'FifthWheel', 'TravelTrailer']

export function vehicleLogKinds(vehicle: VehicleLogSource | null | undefined): VehicleLogKinds {
  const type = vehicle?.vehicle_type ?? ''
  if (!vehicle || !type) {
    return {
      motorized: false,
      fuel: false,
      propane: false,
      def: false,
      defHistory: false,
      odometer: false,
      hours: false,
    }
  }
  const motorized = !(NON_MOTORIZED_TYPES as readonly string[]).includes(type)
  const { tracksDistance, tracksHours } = getUsageTracking(vehicle)
  const def = isDieselFuelType(vehicle.fuel_type) || isDieselFuelType(vehicle.fuel_type_secondary)
  return {
    motorized,
    fuel: motorized && !(NO_FUEL_TYPES as readonly string[]).includes(type),
    propane: PROPANE_TYPES.includes(type),
    def,
    // Kept so legacy DEF history stays visible after a fuel-type change.
    defHistory: def || Number(vehicle.def_tank_capacity_liters ?? 0) > 0,
    odometer: motorized && tracksDistance,
    hours: tracksHours,
  }
}

/** What "add fuel" means on this vehicle: fuel, else DEF, else propane. */
export function fillUpKind(
  kinds: Pick<VehicleLogKinds, 'fuel' | 'def' | 'propane'>,
): 'fuel' | 'def' | 'propane' | null {
  if (kinds.fuel) return 'fuel'
  if (kinds.def) return 'def'
  if (kinds.propane) return 'propane'
  return null
}
