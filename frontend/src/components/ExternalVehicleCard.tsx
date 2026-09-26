import { Phone, Car } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ExternalVehicle } from '../types/externalVehicle'
import { Badge } from './ui'
import { unlessSelectingText } from '../utils/textSelection'
import { yearMakeModel } from '../utils/vehicleLabel'

interface ExternalVehicleCardProps {
  vehicle: ExternalVehicle
  onClick: () => void
}

export default function ExternalVehicleCard({ vehicle, onClick }: ExternalVehicleCardProps) {
  const { t } = useTranslation('vehicles')
  const subtitle = yearMakeModel(vehicle)

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={unlessSelectingText(onClick)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick()
        }
      }}
      className="group relative isolate cursor-pointer overflow-hidden rounded-card border border-border bg-surface ui-motion hover:shadow-card-hover"
    >
      <div className="relative h-[140px] overflow-hidden [background:repeating-linear-gradient(135deg,var(--color-photo-a)_0_13px,var(--color-photo-b)_13px_26px)]">
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-bg via-bg/55 to-transparent" />
        <div className="pointer-events-none absolute left-3 top-3">
          <Badge tone="warning" icon={Car}>
            {t('externalVehicles.referenceBadge')}
          </Badge>
        </div>
        {/* The name and VIN, selectable: `pointer-events-none` here would stop
            the text taking a selection at all (issue #179). The click still
            bubbles to the article, which guards against firing on the click
            that merely ends a selection. */}
        <div className="absolute inset-x-4 bottom-3">
          <h3 className="text-[19px] font-bold tracking-[-.01em] text-text">{vehicle.nickname}</h3>
          {subtitle ? <p className="mt-1 text-sm text-text-mute">{subtitle}</p> : null}
          {vehicle.vin ? (
            <p className="mt-0.5 font-mono text-xs tracking-wide text-text-mute">{vehicle.vin}</p>
          ) : null}
        </div>
      </div>
      <div className="space-y-2 p-4">
        {vehicle.contact_name ? (
          <p className="text-sm text-text-mute">{vehicle.contact_name}</p>
        ) : (
          <p className="text-sm text-text-mute">{t('externalVehicles.referenceContactHint')}</p>
        )}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border pt-3 text-sm text-text-mute">
          {vehicle.contact_phone ? (
            <span className="inline-flex items-center gap-1.5">
              <Phone aria-hidden="true" className="h-3.5 w-3.5" />
              {vehicle.contact_phone}
            </span>
          ) : null}
        </div>
      </div>
    </article>
  )
}
