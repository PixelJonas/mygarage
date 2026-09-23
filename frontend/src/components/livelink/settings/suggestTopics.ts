import type { PresetReadingInfo } from '@/types/livelinkTopicMap'

/**
 * Which topic to suggest for each of a sensor's readings, given its level topic
 * and what the broker was heard publishing.
 *
 * Gateways lay topics out differently. The operator's ESPHome config publishes
 * `.../tank1/level_percent` and `.../tank1/temperature_c`; a Home Assistant-style
 * node publishes `<node>/sensor/propane_level/state` and
 * `<node>/sensor/tank_temperature/state`. What they share is that ONE segment
 * names the reading and the rest is fixed. So the segment of the level topic
 * that names the level (the last one containing a level keyword, else the last
 * segment) is the one that varies, and every other segment must match.
 *
 * - Heard topics in that shape are matched to readings by keyword, each topic
 *   to at most one reading. A reading nothing matches is left out rather than
 *   guessed: a gateway that does not publish it gets no mapping that would
 *   never report. That includes hearing the level alone: the broker was
 *   listening, and nothing else is published there.
 * - When nothing in that shape was heard, not even the level (broker
 *   unreachable, nothing retained), every reading gets a guess from its
 *   reference name in the same shape. The operator chose "suggest, each
 *   editable", so a wrong guess is one edit away.
 *
 * The level reading itself is the input and is never suggested. Pure, so the
 * rules are unit-tested without a broker.
 */
/** Split a level topic and find the segment that varies between readings, or
 *  null when the topic is too short to have a shape. Shared by the suggester
 *  and by the discovery filter, so the two can never disagree about it. */
function shapeOf(
  levelTopic: string,
  readings: PresetReadingInfo[],
): { parts: string[]; vary: number } | null {
  const parts = levelTopic.trim().split('/')
  if (parts.length < 2 || parts.some((segment) => segment === '')) return null
  const keywords = readings.find((r) => r.required)?.keywords ?? []
  let vary = -1
  parts.forEach((segment, index) => {
    if (keywords.some((keyword) => segment.toLowerCase().includes(keyword))) vary = index
  })
  return { parts, vary: vary < 0 ? parts.length - 1 : vary }
}

/**
 * The MQTT filter to listen on for a sensor's other readings: everything under
 * the fixed segments before the one that varies. For the reference layout
 * that is the level topic's own folder.
 */
export function discoveryFilter(levelTopic: string, readings: PresetReadingInfo[]): string | null {
  const shape = shapeOf(levelTopic, readings)
  if (!shape) return null
  return [...shape.parts.slice(0, shape.vary), '#'].join('/')
}

export function suggestTopics(
  levelTopic: string,
  readings: PresetReadingInfo[],
  heard: string[],
): Record<string, string> {
  const topic = levelTopic.trim()
  const shape = shapeOf(topic, readings)
  if (!shape) return {}
  const { parts, vary } = shape

  const levelReading = readings.find((r) => r.required)
  const others = readings.filter((r) => r !== levelReading)
  const named = (segment: string, keywords: readonly string[]): boolean =>
    keywords.some((keyword) => segment.toLowerCase().includes(keyword))

  const inShape = (candidate: string): boolean => {
    const segments = candidate.split('/')
    return (
      segments.length === parts.length &&
      segments.every((segment, index) => index === vary || segment === parts[index])
    )
  }
  const heardInShape = [...new Set(heard)].filter(inShape)
  const candidates = heardInShape.filter((candidate) => candidate !== topic)

  const suggested: Record<string, string> = {}
  if (heardInShape.length === 0) {
    for (const reading of others) {
      suggested[reading.suffix] = parts
        .map((segment, index) => (index === vary ? reading.default_topic : segment))
        .join('/')
    }
    return suggested
  }

  const claimed = new Set<string>()
  for (const reading of others) {
    const match = candidates.find(
      (candidate) => !claimed.has(candidate) && named(candidate.split('/')[vary], reading.keywords),
    )
    if (match) {
      suggested[reading.suffix] = match
      claimed.add(match)
    }
  }
  return suggested
}
