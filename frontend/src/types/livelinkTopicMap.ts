/**
 * Types for config-driven MQTT sources.
 *
 * `TopicMap` is hand-written rather than pulled from `api.generated.ts` because
 * the generated `TopicMapResponse` types `scale`/`value_offset` from the
 * OpenAPI number schema, while the wire carries them as decimal strings.
 */

import type { components } from './api.generated'

export interface TopicMap {
  id: number
  device_id: string
  topic: string
  role: 'telemetry' | 'status'
  param_key: string | null
  value_path: string | null
  unit: string | null
  param_class: string | null
  scale: string
  value_offset: string
  enabled: boolean
}

export interface TopicMapCreate {
  device_id: string
  topic: string
  role?: 'telemetry' | 'status'
  param_key?: string | null
  value_path?: string | null
  unit?: string | null
  param_class?: string | null
  scale?: string
  value_offset?: string
  enabled?: boolean
}

export interface DiscoveredTopic {
  topic: string
  sample: string
}

export interface SourceInfo {
  kind: string
  capabilities: string[]
  /** True when the module already syncs odometer inside store_telemetry. */
  syncs_odometer: boolean
}

/** A sensor template, with the readings one sensor made from it reports. */
export type PresetInfo = components['schemas']['PresetInfo']
export type PresetReadingInfo = components['schemas']['PresetReadingInfo']
/** Adding one sensor: a name, a vehicle, and a topic per reading suffix. */
export type PresetApplyRequest = components['schemas']['PresetApplyRequest']

/** Payloads the backend coerces to 1/0 when they are not numeric. */
const BOOLEANS = new Set([
  'on',
  'off',
  'true',
  'false',
  'online',
  'offline',
  'open',
  'closed',
  'yes',
  'no',
])

/**
 * Whether a discovered sample can become a telemetry value.
 *
 * A convenience warning, not a control: the backend drops uncoercible payloads
 * regardless. Must stay in sync with `_TRUTHY`/`_FALSY` in generic_mqtt.py.
 */
export const isMappableSample = (sample: string): boolean => {
  const trimmed = sample.trim()
  if (trimmed === '') return false
  if (!Number.isNaN(Number(trimmed))) return true
  return BOOLEANS.has(trimmed.toLowerCase())
}

/** Prefill a parameter key from a topic's last segment. */
export const paramKeyFromTopic = (topic: string): string => {
  const tail = topic.split('/').filter(Boolean).pop() ?? ''
  return tail.toUpperCase().replace(/[^A-Z0-9]+/g, '_')
}
