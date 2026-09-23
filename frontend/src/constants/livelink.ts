/**
 * A device id an operator types must be safe as a single URL path segment.
 *
 * Mirrors `DEVICE_ID_PATTERN` in `backend/app/schemas/livelink.py`, which is
 * the authority: every per-device admin route embeds the id in its path, so
 * `rv/gw` routes elsewhere, `gw#1` is cut at the fragment and `""` produces
 * `/devices//readings`. Checking it here names the rule at the field instead
 * of after a round trip. If the two ever disagree, the backend's 422 still
 * reaches the operator through the drawer's error line.
 */
export const DEVICE_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.-]*$/

/** The backend's `max_length` on the same field. */
export const DEVICE_ID_MAX_LENGTH = 20

/**
 * Mirrors the `Field(ge=, le=)` bounds of `LiveLinkSettingsUpdate` in
 * `backend/app/schemas/livelink.py`. Checked on Save so the operator sees the
 * range at the field; the server enforces the same bounds, and its 422 is
 * shown if the two ever drift.
 */
export const SETTINGS_LIMITS = {
  device_offline_timeout_minutes: { min: 5, max: 60 },
  alert_cooldown_minutes: { min: 5, max: 120 },
  session_grace_period_seconds: { min: 0, max: 300 },
  session_gap_minutes: { min: 1, max: 240 },
} as const

export type LimitedSetting = keyof typeof SETTINGS_LIMITS

/**
 * A whole number within `limits`, or null.
 *
 * The WHOLE trimmed string must be digits. `Number.parseInt` reads `20.5` and
 * `20junk` as 20, so an operator who typed either would save a value they did
 * not type and never be told.
 */
export function parseWholeInRange(
  draft: string,
  limits: { min: number; max: number },
): number | null {
  const text = draft.trim()
  if (!/^\d+$/.test(text)) return null
  const value = Number(text)
  return value >= limits.min && value <= limits.max ? value : null
}
