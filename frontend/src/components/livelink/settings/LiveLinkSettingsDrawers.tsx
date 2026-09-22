import type { ReactElement } from 'react'

import type { IntegrationTab } from '@/types/livelink'
import GeneralSettingsDrawer from './GeneralSettingsDrawer'

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
 * exit animation only while it stays mounted itself.
 */

export type SettingsTarget = { type: 'general' } | { type: 'tab'; tab: IntegrationTab }

export function hasDedicatedDrawer(_tab: IntegrationTab): boolean {
  return false
}

interface Props {
  target: SettingsTarget | null
  onClose: () => void
  /** Something a drawer did can change a tab's status: refetch the strip. */
  onChanged: () => void
}

export default function LiveLinkSettingsDrawers({ target, onClose, onChanged }: Props): ReactElement {
  return (
    <GeneralSettingsDrawer
      open={target?.type === 'general'}
      onClose={onClose}
      onChanged={onChanged}
    />
  )
}
