import { useCallback, useEffect, useId, useState } from 'react'
import type { ReactElement } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus } from 'lucide-react'

import { Button, Drawer, Field, Input, Select } from '@/components/ui'
import { DEVICE_ID_MAX_LENGTH, DEVICE_ID_PATTERN } from '@/constants/livelink'
import { livelinkService } from '@/services/livelinkService'
import vehicleService from '@/services/vehicleService'
import type { PresetInfo } from '@/types/livelinkTopicMap'
import type { Vehicle } from '@/types/vehicle'
import { getActionErrorMessage } from '@/utils/httpErrorHandler'

/**
 * Create a LiveLink source: apply a preset, or create a blank device to map
 * by hand.
 *
 * Lives on the card rather than behind a tab because a preset-backed tab only
 * exists once its device does: this is the one entry point that must work with
 * zero devices configured.
 *
 * One device id and one vehicle serve both actions. They are the same two
 * inputs either way, and two fields both named "Device ID" in one drawer read
 * as a duplicate to a screen reader.
 *
 * The vehicle field is not optional decoration. `generic_mqtt` declares
 * `requires_link=True`, and `livelink_ingest.ingest` returns on
 * `requires_link and not device.vin` BEFORE it updates device status, so an
 * unlinked device stores nothing and never leaves `device_status='unknown'`.
 * It stays selectable-as-empty because linking later is legitimate, and the
 * field's hint says what unlinked costs.
 */

interface Props {
  open: boolean
  onClose: () => void
  /** Bumps the card's refreshKey. Without it the new tab does not appear
   *  until the page is reloaded. */
  onCreated: () => void
}

export default function AddSourceDrawer({ open, onClose, onCreated }: Props): ReactElement {
  const { t } = useTranslation('settings')
  const idBase = useId()

  const [presets, setPresets] = useState<PresetInfo[]>([])
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [deviceId, setDeviceId] = useState('')
  const [vin, setVin] = useState('')
  const [label, setLabel] = useState('')

  useEffect(() => {
    if (!open) return
    // Fresh form on every open: the fields describe the NEXT source, and a
    // stale id from the last one invites a 409.
    setDeviceId('')
    setVin('')
    setLabel('')
    setError(null)
    void livelinkService
      .listPresets()
      .then(setPresets)
      .catch(() => setPresets([]))
    void vehicleService
      .list()
      .then((data) => setVehicles(data.vehicles))
      .catch(() => setVehicles([]))
  }, [open])

  const idInvalid = deviceId !== '' && !DEVICE_ID_PATTERN.test(deviceId)
  const ready = deviceId !== '' && !idInvalid && !busy

  const vehicleOptions = vehicles.map((vehicle) => ({
    value: vehicle.vin,
    label: vehicle.nickname || `${vehicle.year} ${vehicle.make} ${vehicle.model}`,
  }))

  const run = useCallback(
    async (action: () => Promise<unknown>): Promise<void> => {
      setError(null)
      setBusy(true)
      try {
        await action()
        onCreated()
        onClose()
      } catch (err) {
        // The server's own words: "Device rvgw already exists" (409) and
        // "Vehicle not found" (404) are both actionable, and a generic
        // "could not create" would hide which one it was.
        setError(getActionErrorMessage(err, t('integrations.addSourceAction')))
      } finally {
        setBusy(false)
      }
    },
    [onCreated, onClose, t],
  )

  const deviceIdField = `${idBase}-device-id`
  const vehicleField = `${idBase}-vehicle`
  const labelField = `${idBase}-label`

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={t('integrations.addSource')}
      icon={Plus}
      closeLabel={t('common:close')}
    >
      <div className="space-y-6">
        {error ? <p className="text-sm text-danger">{error}</p> : null}

        <div>
          <Field
            id={deviceIdField}
            label={t('integrations.mqttDeviceId')}
            hint={t('integrations.deviceIdHint')}
            error={idInvalid ? t('integrations.deviceIdInvalid') : undefined}
          >
            <Input
              id={deviceIdField}
              mono
              value={deviceId}
              maxLength={DEVICE_ID_MAX_LENGTH}
              invalid={idInvalid}
              onChange={(e) => setDeviceId(e.target.value.trim())}
            />
          </Field>

          <Field id={vehicleField} label={t('integrations.sourceVehicle')} hint={t('integrations.sourceVehicleHint')}>
            <Select
              id={vehicleField}
              value={vin}
              onChange={(e) => setVin(e.target.value)}
              placeholder={t('integrations.sourceVehicleUnset')}
              options={vehicleOptions}
            />
          </Field>
        </div>

        <section className="space-y-3">
          <h3 className="text-sm font-semibold text-text">{t('integrations.mqttPresetsHeading')}</h3>
          {presets.map((preset) => {
            const titleId = `${idBase}-preset-${preset.name}`
            return (
              <div key={preset.name} className="rounded-control border border-border p-3">
                <p id={titleId} className="text-sm text-text">
                  {preset.title}
                </p>
                <p className="text-xs text-text-mute">{preset.description}</p>
                <p className="text-xs text-text-mute">
                  {t('integrations.mqttPresetRows', { count: preset.row_count })}
                </p>
                {/* Every preset's button reads "Apply"; the description ties
                    each one to its preset for a screen reader. */}
                <Button
                  className="mt-2"
                  size="sm"
                  aria-describedby={titleId}
                  disabled={!ready}
                  loading={busy}
                  onClick={() =>
                    void run(() => livelinkService.applyPreset(preset.name, deviceId, vin || null))
                  }
                >
                  {t('integrations.mqttApplyPreset')}
                </Button>
              </div>
            )
          })}
        </section>

        <section className="space-y-3 border-t border-border pt-4">
          <h3 className="text-sm font-semibold text-text">{t('integrations.blankSourceHeading')}</h3>
          <p className="text-xs text-text-mute">{t('integrations.blankSourceDescription')}</p>
          <Field id={labelField} label={t('integrations.mqttDeviceLabel')}>
            <Input id={labelField} value={label} maxLength={100} onChange={(e) => setLabel(e.target.value)} />
          </Field>
          <Button
            size="sm"
            variant="secondary"
            disabled={!ready}
            loading={busy}
            onClick={() =>
              void run(() =>
                livelinkService.createDevice({
                  device_id: deviceId,
                  kind: 'generic_mqtt',
                  label: label.trim() || null,
                  vin: vin || null,
                }),
              )
            }
          >
            {t('integrations.mqttCreateDevice')}
          </Button>
        </section>
      </div>
    </Drawer>
  )
}
