/**
 * Scopes a per-vehicle ROUTE that is not VehicleDetail (the analytics page) to
 * that vehicle's odometer unit (#172). Display only, so a failure is safe: with
 * no vehicle and no cached copy it renders unscoped, where the account's units
 * label every number they format.
 */
import { useEffect, useState, type ReactElement, type ReactNode } from 'react'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import vehicleService from '../services/vehicleService'
import { VehicleUnitScope, type VehicleDistanceUnit } from '../contexts/VehicleUnitScope'
import { readCachedVehicle } from '../utils/vehicleCache'

export default function VehicleRouteUnitScope({ children }: { children: ReactNode }): ReactElement {
  const { t } = useTranslation('vehicles')
  const { vin } = useParams<{ vin: string }>()
  const [resolved, setResolved] = useState<{ vin: string; unit: VehicleDistanceUnit } | null>(null)

  useEffect(() => {
    if (!vin) return
    let cancelled = false
    vehicleService
      .get(vin)
      .then((vehicle) => {
        if (!cancelled) setResolved({ vin, unit: vehicle.distance_unit ?? null })
      })
      .catch(() => {
        if (!cancelled) setResolved({ vin, unit: readCachedVehicle(vin)?.distance_unit ?? null })
      })
    return () => {
      cancelled = true
    }
  }, [vin])

  if (!vin) return <>{children}</>
  if (resolved?.vin !== vin) {
    return (
      <div className="flex items-center justify-center min-h-screen" role="status" aria-label={t('detail.loading')}>
        <div className="h-12 w-12 rounded-full border-4 border-[color:var(--accent-solid)] border-t-transparent animate-spin" />
        <span className="sr-only">{t('detail.loading')}</span>
      </div>
    )
  }
  return <VehicleUnitScope distanceUnit={resolved.unit}>{children}</VehicleUnitScope>
}
