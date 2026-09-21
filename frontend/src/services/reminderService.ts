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
  IntervalOverride,
  MaintenanceRuleResponse,
  Reminder,
  ReminderCompleteRequest,
  ReminderCompleteResponse,
  ReminderCreate,
  ReminderPackDetail,
  ReminderPackSummary,
  ReminderUpdate,
  SavePackBody,
} from '../types/reminder'

export type AnchorChoices = Record<string, AnchorChoice | null>
/** Intervals the user retyped while applying, keyed by pack item key. An item
 *  they did not touch is absent, so it keeps the pack's own value. */
export type IntervalOverrides = Record<string, IntervalOverride | null>

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

  /** The vehicle's maintenance rules. The save-as-pack dialog needs the RULES,
   *  not the reminders: a rule is what a pack item becomes, and a rule with no
   *  pending reminder (a mileage rule on a vehicle with no reading) still counts. */
  async listRules(vin: string): Promise<MaintenanceRuleResponse[]> {
    const { data } = await api.get<MaintenanceRuleResponse[]>(
      `/vehicles/${vin}/maintenance-rules`,
    )
    return data
  },

  async listPacks(vehicleType?: string | null): Promise<ReminderPackSummary[]> {
    const params = vehicleType ? { vehicle_type: vehicleType } : undefined
    const { data } = await api.get<ReminderPackSummary[]>('/reminder-packs', { params })
    return data
  },

  async previewPack(
    vin: string,
    packId: string,
    anchors?: AnchorChoices,
    overrides?: IntervalOverrides,
  ): Promise<ApplyPackPreview> {
    const { data } = await api.post<ApplyPackPreview>(
      `/vehicles/${vin}/reminders/apply-pack/preview`,
      { pack_id: packId, anchors: anchors ?? null, overrides: overrides ?? null },
    )
    return data
  },

  async applyPack(
    vin: string,
    packId: string,
    anchors?: AnchorChoices,
    overrides?: IntervalOverrides,
  ): Promise<Reminder[]> {
    const { data } = await api.post<Reminder[]>(`/vehicles/${vin}/reminders/apply-pack`, {
      pack_id: packId,
      anchors: anchors ?? null,
      overrides: overrides ?? null,
    })
    return data
  },

  async savePack(body: SavePackBody): Promise<ReminderPackDetail> {
    const { data } = await api.post<ReminderPackDetail>('/reminder-packs', body)
    return data
  },

  async overwritePack(packId: string, body: SavePackBody): Promise<ReminderPackDetail> {
    const { data } = await api.put<ReminderPackDetail>(`/reminder-packs/${packId}`, body)
    return data
  },

  async renamePack(packId: string, name: string): Promise<ReminderPackDetail> {
    const { data } = await api.patch<ReminderPackDetail>(`/reminder-packs/${packId}`, { name })
    return data
  },

  async deletePack(packId: string): Promise<void> {
    await api.delete(`/reminder-packs/${packId}`)
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
