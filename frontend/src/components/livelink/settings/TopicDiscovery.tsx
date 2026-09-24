import { useId, useState } from 'react'
import type { ReactElement } from 'react'
import { useTranslation } from 'react-i18next'
import { Search } from 'lucide-react'

import { Button, Field, Input } from '@/components/ui'
import { livelinkService } from '@/services/livelinkService'
import type { DiscoveredTopic } from '@/types/livelinkTopicMap'
import { isMappableSample } from '@/types/livelinkTopicMap'

/**
 * Listen to the broker briefly and list what it is publishing.
 *
 * Moved from MqttSourcesCard into the Mosquitto drawer: it is a question about
 * the broker, asked before any device exists. A failed listen now says so;
 * the card's version had no catch, so the rejection went unhandled and the
 * button simply re-enabled.
 */
export default function TopicDiscovery(): ReactElement {
  const { t } = useTranslation('settings')
  const prefixId = useId()
  const [prefix, setPrefix] = useState('')
  const [discovered, setDiscovered] = useState<DiscoveredTopic[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const discover = async (): Promise<void> => {
    setError(null)
    setBusy(true)
    try {
      setDiscovered(await livelinkService.discoverTopics(prefix || '#'))
    } catch {
      setError(t('integrations.discoverFailed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold text-text">{t('integrations.mqttDiscoverHeading')}</h3>
      <Field id={prefixId} label={t('integrations.mqttDiscoverPrefix')}>
        <Input id={prefixId} mono value={prefix} onChange={(e) => setPrefix(e.target.value)} />
      </Field>
      <Button size="sm" variant="secondary" icon={Search} loading={busy} disabled={busy} onClick={() => void discover()}>
        {t('integrations.mqttDiscover')}
      </Button>
      {error ? (
        <p className="text-xs text-danger" role="alert">
          {error}
        </p>
      ) : null}
      <ul className="mt-3 space-y-1">
        {discovered.map((d) => (
          <li key={d.topic} className="text-xs">
            <span className="font-mono text-text-mute">{d.topic}</span>{' '}
            <span className="font-mono">{d.sample}</span>
            {!isMappableSample(d.sample) && (
              <span className="ml-2 text-danger">{t('integrations.mqttErrorsSampleNotNumeric')}</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
