import type { QuickEntryVehicle } from '@/hooks/queries/useQuickEntryVehicles'

/** "Year Make Model", skipping whatever is unknown; empty when nothing is. */
export function yearMakeModel(v: {
  year?: number | null
  make?: string | null
  model?: string | null
}): string {
  return [v.year, v.make, v.model].filter(Boolean).join(' ')
}

/**
 * Human label for a vehicle: "Nickname (Year Make Model)", or just the
 * year/make/model (falling back to the VIN) when the nickname matches or is absent.
 */
export function vehicleLabel(v: QuickEntryVehicle): string {
  const ymm = yearMakeModel(v)
  return v.nickname !== ymm ? `${v.nickname} (${ymm || v.vin})` : ymm || v.vin
}
