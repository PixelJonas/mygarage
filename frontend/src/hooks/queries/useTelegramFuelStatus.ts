import { useQuery } from '@tanstack/react-query'
import api from '@/services/api'
import type { components } from '@/types/api.generated'

export type TelegramFuelStatus = components['schemas']['TelegramFuelStatus']

/**
 * The Telegram fuel-command poller's state. Admin-only on the server.
 * `retry: false` so a refusal is not repeated: an explicit query option wins
 * over the client default (`retry: 1` in App.tsx, `retry: false` in tests).
 */
export function useTelegramFuelStatus() {
  return useQuery({
    queryKey: ['telegram-fuel-status'],
    queryFn: async (): Promise<TelegramFuelStatus> => {
      const { data } = await api.get<TelegramFuelStatus>('/notifications/telegram/fuel-commands')
      return data
    },
    refetchInterval: 15_000,
    retry: false,
  })
}
