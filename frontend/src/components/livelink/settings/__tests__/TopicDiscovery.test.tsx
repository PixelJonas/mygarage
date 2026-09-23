import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const discoverTopics = vi.fn()
vi.mock('@/services/livelinkService', () => ({
  livelinkService: { discoverTopics: (prefix: string) => discoverTopics(prefix) },
}))

import TopicDiscovery from '../TopicDiscovery'

beforeEach(() => {
  vi.clearAllMocks()
  discoverTopics.mockResolvedValue([])
})

describe('TopicDiscovery', () => {
  it('warns that a discovered non-numeric topic cannot be mapped', async () => {
    discoverTopics.mockResolvedValue([{ topic: 'mygarage/rv/gateway/ip', sample: '10.10.20.243' }])
    render(<TopicDiscovery />)

    fireEvent.click(screen.getByRole('button', { name: 'integrations.mqttDiscover' }))

    expect(await screen.findByText('integrations.mqttErrorsSampleNotNumeric')).toBeInTheDocument()
  })

  it('listens to everything when no prefix is given', async () => {
    render(<TopicDiscovery />)

    fireEvent.click(screen.getByRole('button', { name: 'integrations.mqttDiscover' }))

    await waitFor(() => expect(discoverTopics).toHaveBeenCalledWith('#'))
  })

  it('says so when the broker cannot be reached', async () => {
    // The card this came from had no catch: the rejection went unhandled and
    // the button quietly re-enabled.
    discoverTopics.mockRejectedValue(new Error('timeout'))
    render(<TopicDiscovery />)

    fireEvent.click(screen.getByRole('button', { name: 'integrations.mqttDiscover' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('integrations.discoverFailed')
  })
})
