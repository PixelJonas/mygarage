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
