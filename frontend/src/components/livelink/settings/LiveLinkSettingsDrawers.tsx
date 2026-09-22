import { useState } from 'react'
import type { ReactElement } from 'react'

import type { IntegrationTab } from '@/types/livelink'
import GeneralSettingsDrawer from './GeneralSettingsDrawer'
import MosquittoSettingsDrawer from './MosquittoSettingsDrawer'
import WicanSettingsDrawer from './WicanSettingsDrawer'

/**
 * Picks the settings drawer for what the operator clicked: the gear on the
 * LiveLink card, or one tab's Settings button.
 *
 * One switch, so the old modal fallback has exactly one place to shrink from.
 * Until the last per-source drawer lands, a tab with no dedicated drawer
 * still opens LiveLinkSettingsModal; `hasDedicatedDrawer` is how the settings
 * tab knows which.
 *
 * Every drawer stays mounted with `open` derived from the target, rather than
 * being rendered conditionally: `Drawer` keeps its panel in the tree for the
 * exit animation only while it stays mounted itself. For the same reason the
 * last opened tab is remembered, so a closing drawer keeps its title.
 */

export type SettingsTarget = { type: 'general' } | { type: 'tab'; tab: IntegrationTab }

type DrawerKind = 'broker' | 'wican'

/** Which dedicated drawer a tab opens, or null for the old modal. */
function drawerFor(tab: IntegrationTab): DrawerKind | null {
  if (tab.id === 'broker') return 'broker'
  if (tab.id === 'wican') return 'wican'
  return null
}

export function hasDedicatedDrawer(tab: IntegrationTab): boolean {
  return drawerFor(tab) !== null
}

interface Props {
  target: SettingsTarget | null
  onClose: () => void
  /** Something a drawer did can change a tab's status: refetch the strip. */
  onChanged: () => void
}

export default function LiveLinkSettingsDrawers({ target, onClose, onChanged }: Props): ReactElement {
  // Adjusting state during render (React's documented pattern for "remember
  // something from a previous render"), not a ref: refs are not read in render.
  const [lastTab, setLastTab] = useState<IntegrationTab | null>(null)
  if (target?.type === 'tab' && target.tab !== lastTab) setLastTab(target.tab)
  const openKind = target?.type === 'tab' ? drawerFor(target.tab) : null

  return (
    <>
      <GeneralSettingsDrawer open={target?.type === 'general'} onClose={onClose} onChanged={onChanged} />
      <MosquittoSettingsDrawer
        open={openKind === 'broker'}
        tab={lastTab}
        onClose={onClose}
        onChanged={onChanged}
      />
      <WicanSettingsDrawer open={openKind === 'wican'} tab={lastTab} onClose={onClose} onChanged={onChanged} />
    </>
  )
}
