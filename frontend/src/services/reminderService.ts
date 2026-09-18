/**
 * Reminder API service, plus the maintenance lifecycle around reminders:
 * completion with the real date and readings, pack preview and apply,
 * duplicate reconciliation, and the canonical maintenance types.
 */

import api from './api'
import type {
  AnchorChoice,
  ApplyPackPreview,
  DuplicateGroup,
  MaintenanceTypeOption,
  Reminder,
  ReminderCompleteRequest,
  ReminderCompleteResponse,
  ReminderCreate,
  ReminderPackSummary,
  ReminderUpdate,
} from '../types/reminder'

export type AnchorChoices = Record<string, AnchorChoice | null>

export const reminderService = {
  async list(vin: string, status?: string): Promise<Reminder[]> {
    const params = status ? { status } : undefined
    const { data } = await api.get<Reminder[]>(`/vehicles/${vin}/reminders`, { params })
    return data
  },

  async create(vin: string, payload: ReminderCreate): Promise<Reminder> {
    const { data } = await api.post<Reminder>(`/vehicles/${vin}/reminders`, payload)
    return data
  },

  async update(vin: string, id: number, payload: ReminderUpdate): Promise<Reminder> {
    const { data } = await api.put<Reminder>(`/vehicles/${vin}/reminders/${id}`, payload)
    return data
  },

  async remove(vin: string, id: number): Promise<void> {
    await api.delete(`/vehicles/${vin}/reminders/${id}`)
  },

  async markDone(vin: string, id: number): Promise<Reminder> {
    const { data } = await api.post<Reminder>(`/vehicles/${vin}/reminders/${id}/done`)
    return data
  },

  async dismiss(vin: string, id: number): Promise<Reminder> {
    const { data } = await api.post<Reminder>(`/vehicles/${vin}/reminders/${id}/dismiss`)
    return data
  },

  /** Hide a pending reminder from every nag surface until a date (exclusive). */
  async snooze(vin: string, id: number, until: string): Promise<Reminder> {
    const { data } = await api.post<Reminder>(`/vehicles/${vin}/reminders/${id}/snooze`, { until })
    return data
  },

  async unsnooze(vin: string, id: number): Promise<Reminder> {
    const { data } = await api.post<Reminder>(`/vehicles/${vin}/reminders/${id}/unsnooze`)
    return data
  },

  async complete(
    vin: string,
    id: number,
    payload: ReminderCompleteRequest,
  ): Promise<ReminderCompleteResponse> {
    const { data } = await api.post<ReminderCompleteResponse>(
      `/vehicles/${vin}/reminders/${id}/complete`,
      payload,
    )
    return data
  },

  async listPacks(vehicleType?: string | null): Promise<ReminderPackSummary[]> {
    const params = vehicleType ? { vehicle_type: vehicleType } : undefined
    const { data } = await api.get<ReminderPackSummary[]>('/reminder-packs', { params })
    return data
  },

  async previewPack(vin: string, packId: string, anchors?: AnchorChoices): Promise<ApplyPackPreview> {
    const { data } = await api.post<ApplyPackPreview>(
      `/vehicles/${vin}/reminders/apply-pack/preview`,
      { pack_id: packId, anchors: anchors ?? null },
    )
    return data
  },

  async applyPack(vin: string, packId: string, anchors?: AnchorChoices): Promise<Reminder[]> {
    const { data } = await api.post<Reminder[]>(`/vehicles/${vin}/reminders/apply-pack`, {
      pack_id: packId,
      anchors: anchors ?? null,
    })
    return data
  },

  async duplicates(vin: string): Promise<DuplicateGroup[]> {
    const { data } = await api.get<DuplicateGroup[]>(`/vehicles/${vin}/reminders/duplicates`)
    return data
  },

  async reconcileDuplicates(vin: string, keepId: number, supersedeIds: number[]): Promise<Reminder[]> {
    const { data } = await api.post<Reminder[]>(`/vehicles/${vin}/reminders/reconcile-duplicates`, {
      keep_id: keepId,
      supersede_ids: supersedeIds,
    })
    return data
  },

  async reconcile(vin: string): Promise<Reminder[]> {
    const { data } = await api.post<Reminder[]>(`/vehicles/${vin}/reminders/reconcile`)
    return data
  },

  async maintenanceTypes(): Promise<MaintenanceTypeOption[]> {
    const { data } = await api.get<MaintenanceTypeOption[]>('/maintenance-types')
    return data
  },
}
