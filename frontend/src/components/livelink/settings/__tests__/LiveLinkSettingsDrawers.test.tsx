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
  it('opens the general drawer for the gear', () => {
    render(<LiveLinkSettingsDrawers target={{ type: 'general' }} onClose={vi.fn()} onChanged={vi.fn()} />)
    expect(screen.getByText('general-drawer')).toBeInTheDocument()
  })

  it('opens nothing when there is no target', () => {
    render(<LiveLinkSettingsDrawers target={null} onClose={vi.fn()} onChanged={vi.fn()} />)
    expect(screen.queryByText('general-drawer')).not.toBeInTheDocument()
  })

  it('sends every source tab to the old modal until its drawer exists', () => {
    for (const t of [
      tab('wican', 'wican'),
      tab('torque', 'torque'),
      tab('broker', null),
      tab('device:rvgw', 'generic_mqtt'),
    ]) {
      expect(hasDedicatedDrawer(t), t.id).toBe(false)
    }
  })
})
