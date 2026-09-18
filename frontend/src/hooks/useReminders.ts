/**
 * React Query hooks for vehicle reminders and the maintenance lifecycle.
 *
 * A completion writes a service visit and a reading as well as reminders, so
 * the completion, pack and reconcile mutations invalidate the visit and
 * reading queries too; the visit mutations (`queries/useServiceVisits`)
 * invalidate reminders in return, since a typed service moves them.
 */

import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { reminderService, type AnchorChoices } from '../services/reminderService'
import type { ReminderCompleteRequest, ReminderCreate, ReminderUpdate } from '../types/reminder'

/** Every query a maintenance write can move. */
export function invalidateMaintenanceQueries(queryClient: QueryClient, vin: string): void {
  for (const key of [
    'reminders',
    'reminderDuplicates',
    'packPreview',
    'serviceVisits',
    'latestMileage',
    'latestHours',
    'odometerRecords',
    'hoursRecords',
  ]) {
    void queryClient.invalidateQueries({ queryKey: [key, vin] })
  }
}

export function useReminders(vin: string, status?: string) {
  return useQuery({
    queryKey: ['reminders', vin, status],
    queryFn: () => reminderService.list(vin, status),
    enabled: !!vin,
  })
}

export function useCreateReminder(vin: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ReminderCreate) => reminderService.create(vin, payload),
    onSuccess: () => invalidateMaintenanceQueries(queryClient, vin),
  })
}

export function useUpdateReminder(vin: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...payload }: ReminderUpdate & { id: number }) =>
      reminderService.update(vin, id, payload),
    onSuccess: () => invalidateMaintenanceQueries(queryClient, vin),
  })
}

export function useDeleteReminder(vin: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => reminderService.remove(vin, id),
    onSuccess: () => invalidateMaintenanceQueries(queryClient, vin),
  })
}

export function useMarkReminderDone(vin: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => reminderService.markDone(vin, id),
    onSuccess: () => invalidateMaintenanceQueries(queryClient, vin),
  })
}

export function useMarkReminderDismissed(vin: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => reminderService.dismiss(vin, id),
    onSuccess: () => invalidateMaintenanceQueries(queryClient, vin),
  })
}

export function useSnoozeReminder(vin: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, until }: { id: number; until: string }) =>
      reminderService.snooze(vin, id, until),
    onSuccess: () => invalidateMaintenanceQueries(queryClient, vin),
  })
}

export function useUnsnoozeReminder(vin: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => reminderService.unsnooze(vin, id),
    onSuccess: () => invalidateMaintenanceQueries(queryClient, vin),
  })
}

export function useCompleteReminder(vin: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...payload }: ReminderCompleteRequest & { id: number }) =>
      reminderService.complete(vin, id, payload),
    onSuccess: () => invalidateMaintenanceQueries(queryClient, vin),
  })
}

export function useReminderPacks(vehicleType: string | null | undefined) {
  return useQuery({
    queryKey: ['reminderPacks', vehicleType ?? ''],
    queryFn: () => reminderService.listPacks(vehicleType),
  })
}

export function usePackPreview(vin: string, packId: string | null, anchors: AnchorChoices) {
  return useQuery({
    // TanStack hashes plain objects with sorted keys, so the choice order is irrelevant.
    queryKey: ['packPreview', vin, packId, anchors],
    queryFn: () => reminderService.previewPack(vin, packId as string, anchors),
    enabled: !!vin && !!packId,
    staleTime: 0,
  })
}

export function useApplyPack(vin: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ packId, anchors }: { packId: string; anchors?: AnchorChoices }) =>
      reminderService.applyPack(vin, packId, anchors),
    onSuccess: () => invalidateMaintenanceQueries(queryClient, vin),
  })
}

export function useReminderDuplicates(vin: string) {
  return useQuery({
    queryKey: ['reminderDuplicates', vin],
    queryFn: () => reminderService.duplicates(vin),
    enabled: !!vin,
  })
}

export function useReconcileDuplicates(vin: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ keepId, supersedeIds }: { keepId: number; supersedeIds: number[] }) =>
      reminderService.reconcileDuplicates(vin, keepId, supersedeIds),
    onSuccess: () => invalidateMaintenanceQueries(queryClient, vin),
  })
}

export function useMaintenanceTypes() {
  return useQuery({
    queryKey: ['maintenanceTypes'],
    queryFn: () => reminderService.maintenanceTypes(),
    staleTime: 24 * 60 * 60 * 1000,
  })
}
