import { useCallback, useEffect, useState } from 'react'
import type { ReactElement } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Settings } from 'lucide-react'

import Button from '@/components/ui/Button'
import Tabs from '@/components/ui/Tabs'
import { livelinkService } from '@/services/livelinkService'
import type { IntegrationTab } from '@/types/livelink'
import { DOT_TONE, STATUS_KEY } from './integrationStatus'

/**
 * The LiveLink card's tab strip.
 *
 * Tabs, their status and their counts are all derived by the backend
 * (`GET /api/livelink/integrations`), so a new preset produces a new tab with
 * no change here.
 *
 * The dot is decorative: it is `aria-hidden` inside `Tabs`, so the detail line
 * below states the status in words. Counts alone cannot do that job, because a
 * disabled integration keeps the online count it had before it was switched
 * off, and the broker has no devices at all.
 */

/** Literal keys, as in STATUS_KEY (./integrationStatus): `validate-i18n-usage`
 *  resolves `descriptionKey:` fields by name, and a computed key would be
 *  invisible to it. */
const SOURCE_DESCRIPTIONS: Record<string, { descriptionKey: string }> = {
  wican: { descriptionKey: 'integrations.sourceWicanDescription' },
  torque: { descriptionKey: 'integrations.sourceTorqueDescription' },
  broker: { descriptionKey: 'integrations.sourceBrokerDescription' },
}

interface Props {
  onOpenSettings: (tab: IntegrationTab) => void
  /** Omit and no Add-source button renders: a button with nowhere to go is
   *  worse than none. */
  onAddSource?: () => void
  /** Bump to refetch after a mutation elsewhere changes the strip. */
  refreshKey?: number
}

export default function LiveLinkIntegrationsCard({
  onOpenSettings,
  onAddSource,
  refreshKey = 0,
}: Props): ReactElement {
  const { t } = useTranslation('settings')
  const [tabs, setTabs] = useState<IntegrationTab[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  const load = useCallback(async (): Promise<void> => {
    try {
      const data = await livelinkService.getIntegrations()
      setTabs(data.tabs)
      setFailed(false)
      // Keep the operator's tab across a refetch; fall back to the first only
      // when theirs has gone (a deleted device's tab).
      setActiveId((current) =>
        current && data.tabs.some((tab) => tab.id === current)
          ? current
          : (data.tabs[0]?.id ?? null),
      )
    } catch {
      // This card is one of six on the settings tab. A failure here must not
      // take the others with it (G8).
      setFailed(true)
      setTabs([])
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load, refreshKey])

  const active = tabs.find((tab) => tab.id === activeId) ?? null

  const describe = (tab: IntegrationTab): string => {
    const entry = SOURCE_DESCRIPTIONS[tab.id]
    if (entry) return t(entry.descriptionKey)
    return tab.description ?? ''
  }

  return (
    <div className="space-y-4">
      {failed ? (
        <div className="space-y-2">
          <p className="text-sm text-text-mute">{t('integrations.integrationsLoadError')}</p>
          <Button size="sm" variant="secondary" onClick={() => void load()}>
            {t('common:retry')}
          </Button>
        </div>
      ) : null}

      {tabs.length > 0 && activeId ? (
        <Tabs
          items={tabs.map((tab) => ({
            id: tab.id,
            label: tab.label,
            dot: DOT_TONE[tab.status] ?? 'danger',
          }))}
          activeId={activeId}
          onChange={setActiveId}
          label={t('integrations.livelink')}
          variant="pill"
        />
      ) : null}

      {active ? (
        <div className="space-y-2">
          <p className="text-sm text-text">{describe(active)}</p>
          <p className="text-sm text-text-mute">
            {t(STATUS_KEY[active.reason] ?? 'integrations.statusNotConfigured')}
          </p>
          {/* LINKED devices, not all of them. Counting every device put
              "2 devices linked" under "Not linked to a vehicle". A tab with no
              devices (the broker) has nothing to count. */}
          {active.device_count > 0 ? (
            <p className="text-sm text-text-mute">
              {t('integrationsTab.devicesLinked', { count: active.linked_count })}
              {active.online_count > 0
                ? t('integrationsTab.devicesOnlineSuffix', { count: active.online_count })
                : null}
            </p>
          ) : null}
          <Button size="sm" icon={Settings} onClick={() => onOpenSettings(active)}>
            {t('integrations.sourceSettings', { source: active.label })}
          </Button>
        </div>
      ) : null}

      {/* Outside the tab body on purpose. A preset-backed tab exists only once
          its device does, so the control that creates one cannot live behind a
          tab, or a fresh install has no way in. */}
      {onAddSource ? (
        <div className="border-t border-border pt-3">
          <Button size="sm" variant="secondary" icon={Plus} onClick={onAddSource}>
            {t('integrations.addSource')}
          </Button>
        </div>
      ) : null}
    </div>
  )
}
