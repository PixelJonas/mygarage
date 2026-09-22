import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Radio, Search, Trash2 } from 'lucide-react'

import Button from '@/components/ui/Button'
import Card from '@/components/ui/Card'
import Input from '@/components/ui/Input'
import { livelinkService } from '@/services/livelinkService'
import type {
  DiscoveredTopic,
  PresetInfo,
  TopicMap,
} from '@/types/livelinkTopicMap'
import { isMappableSample, paramKeyFromTopic } from '@/types/livelinkTopicMap'

/**
 * Add and edit config-driven MQTT sources.
 *
 * A `generic_mqtt` device declares neither AUTO_DISCOVER nor a token flow, so
 * unlike WiCAN it cannot appear on its own. Without the create form here the
 * only way such a device can exist is by applying a preset, and mappings saved
 * against a device id that does not exist are silently discarded at ingest.
 *
 * Gauges, charts and threshold alerts need no work here: a mapped topic becomes
 * an ordinary `livelink_parameters` row and flows into the existing LiveLink
 * tabs unchanged.
 */

interface Props {
  /** Device whose mappings are shown. Null shows only the create form. */
  deviceId: string | null
}

export function MqttSourcesCard({ deviceId }: Props): React.ReactElement {
  const { t } = useTranslation('settings')

  const [maps, setMaps] = useState<TopicMap[]>([])
  const [presets, setPresets] = useState<PresetInfo[]>([])
  const [discovered, setDiscovered] = useState<DiscoveredTopic[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const [newDeviceId, setNewDeviceId] = useState('')
  const [newLabel, setNewLabel] = useState('')

  const [topic, setTopic] = useState('')
  const [paramKey, setParamKey] = useState('')
  const [paramKeyTouched, setParamKeyTouched] = useState(false)
  const [unit, setUnit] = useState('')

  const [prefix, setPrefix] = useState('')

  // Every loader swallows its error and falls back to an empty list. A card
  // that blanks the page because one fetch failed is worse than a card that
  // shows nothing to map yet, and this component is mounted inside a settings
  // tab whose other sections must keep rendering.
  const refresh = useCallback(async (): Promise<void> => {
    if (!deviceId) {
      setMaps([])
      return
    }
    try {
      setMaps(await livelinkService.listTopicMaps(deviceId))
    } catch {
      setMaps([])
    }
  }, [deviceId])

  useEffect(() => {
    void refresh()
    void livelinkService
      .listPresets()
      .then(setPresets)
      .catch(() => setPresets([]))
  }, [refresh])

  // Prefill the parameter key from the topic's last segment until the user
  // edits it themselves.
  useEffect(() => {
    if (!paramKeyTouched) setParamKey(paramKeyFromTopic(topic))
  }, [topic, paramKeyTouched])

  const createDevice = async (): Promise<void> => {
    setError(null)
    setBusy(true)
    try {
      // vin is optional: an unlinked device is a valid intermediate state, the
      // same one a freshly auto-discovered WiCAN sits in before it is linked.
      await livelinkService.createDevice({
        device_id: newDeviceId,
        kind: 'generic_mqtt',
        label: newLabel || null,
      })
      setNewDeviceId('')
      setNewLabel('')
    } finally {
      setBusy(false)
    }
  }

  const addMapping = async (): Promise<void> => {
    setError(null)
    // Mapped topics are EXACT. Rejecting here as well as server-side keeps the
    // reason next to the field the user just typed in.
    if (topic.includes('+') || topic.includes('#')) {
      setError(t('integrations.mqttErrorsTopicMustBeExact'))
      return
    }
    if (!deviceId) return
    setBusy(true)
    try {
      await livelinkService.createTopicMap({
        device_id: deviceId,
        topic,
        param_key: paramKey,
        unit: unit || null,
      })
      setTopic('')
      setParamKeyTouched(false)
      setUnit('')
      await refresh()
    } finally {
      setBusy(false)
    }
  }

  const discover = async (): Promise<void> => {
    setError(null)
    setBusy(true)
    try {
      setDiscovered(await livelinkService.discoverTopics(prefix || '#'))
    } finally {
      setBusy(false)
    }
  }

  const remove = async (id: number): Promise<void> => {
    await livelinkService.deleteTopicMap(id)
    await refresh()
  }

  const applyPreset = async (name: string): Promise<void> => {
    setBusy(true)
    try {
      await livelinkService.applyPreset(name, newDeviceId || 'rvgw')
      await refresh()
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <h3 className="text-sm font-semibold text-text mb-1 flex items-center gap-2">
        <Radio className="h-4 w-4" aria-hidden="true" />
        {t('integrations.mqttTitle')}
      </h3>
      <p className="text-xs text-text-mute mb-4">{t('integrations.mqttDescription')}</p>

      {error && (
        <p className="text-xs text-danger mb-3" role="alert">
          {error}
        </p>
      )}

      <section className="mb-6">
        <h4 className="text-xs font-semibold text-text mb-2">
          {t('integrations.mqttCreateDeviceHeading')}
        </h4>
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="text-xs text-text-mute">
            {t('integrations.mqttDeviceId')}
            <Input value={newDeviceId} onChange={(e) => setNewDeviceId(e.target.value)} />
          </label>
          <label className="text-xs text-text-mute">
            {t('integrations.mqttDeviceLabel')}
            <Input value={newLabel} onChange={(e) => setNewLabel(e.target.value)} />
          </label>
        </div>
        <Button className="mt-2" size="sm" disabled={busy} onClick={() => void createDevice()}>
          {t('integrations.mqttCreateDevice')}
        </Button>
      </section>

      <section className="mb-6">
        <h4 className="text-xs font-semibold text-text mb-2">
          {t('integrations.mqttMappingsHeading')}
        </h4>
        <ul className="mb-3 space-y-1">
          {maps.map((m) => (
            <li key={m.id} className="flex items-center justify-between text-xs">
              <span className="font-mono text-text-mute">{m.topic}</span>
              <span className="font-mono text-text">{m.param_key}</span>
              <Button
                size="sm"
                variant="ghost"
                icon={Trash2}
                aria-label={t('integrations.mqttRemoveMapping')}
                onClick={() => void remove(m.id)}
              />
            </li>
          ))}
        </ul>
        <div className="grid gap-2 sm:grid-cols-3">
          <label className="text-xs text-text-mute">
            {t('integrations.mqttMapTopic')}
            <Input value={topic} onChange={(e) => setTopic(e.target.value)} />
          </label>
          <label className="text-xs text-text-mute">
            {t('integrations.mqttParamKey')}
            <Input
              value={paramKey}
              onChange={(e) => {
                setParamKeyTouched(true)
                setParamKey(e.target.value)
              }}
            />
          </label>
          <label className="text-xs text-text-mute">
            {t('integrations.mqttUnit')}
            <Input value={unit} onChange={(e) => setUnit(e.target.value)} />
          </label>
        </div>
        <Button className="mt-2" size="sm" disabled={busy} onClick={() => void addMapping()}>
          {t('integrations.mqttAddMapping')}
        </Button>
      </section>

      <section className="mb-6">
        <h4 className="text-xs font-semibold text-text mb-2">
          {t('integrations.mqttDiscoverHeading')}
        </h4>
        <label className="text-xs text-text-mute">
          {t('integrations.mqttDiscoverPrefix')}
          <Input value={prefix} onChange={(e) => setPrefix(e.target.value)} />
        </label>
        <Button
          className="mt-2"
          size="sm"
          variant="secondary"
          icon={Search}
          disabled={busy}
          onClick={() => void discover()}
        >
          {t('integrations.mqttDiscover')}
        </Button>
        <ul className="mt-3 space-y-1">
          {discovered.map((d) => (
            <li key={d.topic} className="text-xs">
              <span className="font-mono text-text-mute">{d.topic}</span>{' '}
              <span className="font-mono">{d.sample}</span>
              {!isMappableSample(d.sample) && (
                <span className="ml-2 text-danger">
                  {t('integrations.mqttErrorsSampleNotNumeric')}
                </span>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h4 className="text-xs font-semibold text-text mb-2">
          {t('integrations.mqttPresetsHeading')}
        </h4>
        <ul className="space-y-1">
          {presets.map((p) => (
            <li key={p.name} className="flex items-center justify-between text-xs">
              <span>
                {p.title}{' '}
                <span className="text-text-mute">
                  {t('integrations.mqttPresetRows', { count: p.row_count })}
                </span>
              </span>
              <Button size="sm" disabled={busy} onClick={() => void applyPreset(p.name)}>
                {t('integrations.mqttApplyPreset')}
              </Button>
            </li>
          ))}
        </ul>
      </section>
    </Card>
  )
}

export default MqttSourcesCard
