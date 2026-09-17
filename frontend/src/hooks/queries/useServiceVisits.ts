import { useInfiniteQuery, useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '@/services/api'
import { invalidateMaintenanceQueries } from '@/hooks/useReminders'
import type { ServiceVisitListResponse, ServiceVisitCreate, ServiceVisitUpdate } from '@/types/serviceVisit'

export function useServiceVisits(vin: string) {
  return useQuery({
    queryKey: ['serviceVisits', vin],
    queryFn: async () => {
      const { data } = await api.get<ServiceVisitListResponse>(
        `/vehicles/${vin}/service-visits`
      )
      return data
    },
    enabled: !!vin,
  })
}

const VISIT_PAGE_SIZE = 100

/**
 * Every visit of the vehicle, newest first, a page at a time: for a picker
 * that must be able to reach a visit older than the first page. Keyed under
 * `['serviceVisits', vin]` so every visit write invalidates it too.
 */
export function useServiceVisitPages(vin: string, options: { enabled?: boolean } = {}) {
  return useInfiniteQuery({
    queryKey: ['serviceVisits', vin, 'pages'],
    queryFn: async ({ pageParam }) => {
      const { data } = await api.get<ServiceVisitListResponse>(`/vehicles/${vin}/service-visits`, {
        params: { skip: pageParam, limit: VISIT_PAGE_SIZE },
      })
      return data
    },
    initialPageParam: 0,
    getNextPageParam: (last, pages) => {
      const loaded = pages.reduce((n, page) => n + page.visits.length, 0)
      return loaded < last.total ? loaded : undefined
    },
    enabled: !!vin && (options.enabled ?? true),
  })
}

export function useCreateServiceVisit(vin: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (payload: ServiceVisitCreate) => {
      const { data } = await api.post(`/vehicles/${vin}/service-visits`, payload)
      return data
    },
    // A typed service is the newest event of a rule's type: it can complete
    // a pending reminder and create the next one, so reminders (and the
    // readings the visit synced) are invalidated with the visits.
    onSuccess: () => invalidateMaintenanceQueries(queryClient, vin),
  })
}

export function useUpdateServiceVisit(vin: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, ...payload }: ServiceVisitUpdate & { id: number }) => {
      const { data } = await api.put(`/vehicles/${vin}/service-visits/${id}`, payload)
      return data
    },
    // A typed service is the newest event of a rule's type: it can complete
    // a pending reminder and create the next one, so reminders (and the
    // readings the visit synced) are invalidated with the visits.
    onSuccess: () => invalidateMaintenanceQueries(queryClient, vin),
  })
}

export function useDeleteServiceVisit(vin: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (visitId: number) => {
      await api.delete(`/vehicles/${vin}/service-visits/${visitId}`)
    },
    // A typed service is the newest event of a rule's type: it can complete
    // a pending reminder and create the next one, so reminders (and the
    // readings the visit synced) are invalidated with the visits.
    onSuccess: () => invalidateMaintenanceQueries(queryClient, vin),
  })
}
