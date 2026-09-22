import { useState } from 'react'
import type { ReactElement } from 'react'

import type { IntegrationTab } from '@/types/livelink'
import GeneralSettingsDrawer from './GeneralSettingsDrawer'
import MosquittoSettingsDrawer from './MosquittoSettingsDrawer'
import MqttDeviceDrawer from './MqttDeviceDrawer'
import SourceDevicesDrawer from './SourceDevicesDrawer'
import TorqueSettingsDrawer from './TorqueSettingsDrawer'
import WicanSettingsDrawer from './WicanSettingsDrawer'

/**
 * Picks the settings drawer for what the operator clicked: the gear on the
 * LiveLink card, or one tab's Settings button. Every tab has one: the built-in
 * sources and the broker their own, each MQTT device the MQTT device drawer,
 * and any other registered kind the device-list fallback (spec G2).
 *
 * Every drawer stays mounted with `open` derived from the target, rather than
 * being rendered conditionally: `Drawer` keeps its panel in the tree for the
 * exit animation only while it stays mounted itself. For the same reason the
 * last opened tab is remembered, so a closing drawer keeps its title.
 */

export type SettingsTarget = { type: 'general' } | { type: 'tab'; tab: IntegrationTab }

type DrawerKind = 'broker' | 'wican' | 'torque' | 'mqtt' | 'devices'

/** Which drawer a tab opens. Total: no tab is left without one. */
function drawerFor(tab: IntegrationTab): DrawerKind {
  if (tab.id === 'broker') return 'broker'
  if (tab.id === 'wican') return 'wican'
  if (tab.id === 'torque') return 'torque'
  // One tab per MQTT device, preset-made (Mopeka) or mapped by hand.
  if (tab.kind === 'generic_mqtt') return 'mqtt'
  // Any other registered kind: its devices, and no bespoke settings (spec G2).
  return 'devices'
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
      <TorqueSettingsDrawer open={openKind === 'torque'} tab={lastTab} onClose={onClose} onChanged={onChanged} />
      <MqttDeviceDrawer open={openKind === 'mqtt'} tab={lastTab} onClose={onClose} onChanged={onChanged} />
      <SourceDevicesDrawer open={openKind === 'devices'} tab={lastTab} onClose={onClose} onChanged={onChanged} />
    </>
  )
}
