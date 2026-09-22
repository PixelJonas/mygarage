/**
 * The router from a settings target to its drawer.
 *
 * Each drawer is stubbed to render its name ONLY when open, as a real closed
 * Drawer renders nothing. A stub that always rendered would let a router that
 * opens every drawer pass.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { IntegrationTab } from '@/types/livelink'

vi.mock('../GeneralSettingsDrawer', () => ({
  default: ({ open }: { open: boolean }) => (open ? <p>general-drawer</p> : null),
}))
vi.mock('../MosquittoSettingsDrawer', () => ({
  default: ({ open }: { open: boolean }) => (open ? <p>mosquitto-drawer</p> : null),
}))

const DRAWERS = ['general-drawer', 'mosquitto-drawer']

/** Exactly `expected` renders, and no other drawer. */
const expectOnly = (expected: string | null): void => {
  for (const name of DRAWERS) {
    if (name === expected) expect(screen.getByText(name)).toBeInTheDocument()
    else expect(screen.queryByText(name), name).not.toBeInTheDocument()
  }
}

import LiveLinkSettingsDrawers, { hasDedicatedDrawer } from '../LiveLinkSettingsDrawers'

const tab = (id: string, kind: string | null): IntegrationTab =>
  ({
    id,
    label: id,
    kind,
    status: 'ok',
    reason: 'receiving',
    description: null,
    device_count: 0,
    online_count: 0,
    linked_count: 0,
    firmware_updates: 0,
  }) as IntegrationTab

describe('LiveLinkSettingsDrawers', () => {
  it('opens the general drawer for the gear, and only it', () => {
    render(<LiveLinkSettingsDrawers target={{ type: 'general' }} onClose={vi.fn()} onChanged={vi.fn()} />)
    expectOnly('general-drawer')
  })

  it('opens nothing when there is no target', () => {
    render(<LiveLinkSettingsDrawers target={null} onClose={vi.fn()} onChanged={vi.fn()} />)
    expectOnly(null)
  })

  it('opens the Mosquitto drawer for the broker tab, and only it', () => {
    const broker = tab('broker', null)
    render(<LiveLinkSettingsDrawers target={{ type: 'tab', tab: broker }} onClose={vi.fn()} onChanged={vi.fn()} />)
    expectOnly('mosquitto-drawer')
    expect(hasDedicatedDrawer(broker)).toBe(true)
  })

  it('sends the other source tabs to the old modal until their drawers exist', () => {
    for (const t of [tab('wican', 'wican'), tab('torque', 'torque'), tab('device:rvgw', 'generic_mqtt')]) {
      expect(hasDedicatedDrawer(t), t.id).toBe(false)
    }
  })
})
