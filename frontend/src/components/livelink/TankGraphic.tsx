import { useId } from 'react'
import type { ReactElement } from 'react'

import { formatAtPrecision } from '@/utils/unitFormat'
import type { TankTone } from '@/utils/sensorReadings'

/**
 * An upright propane bottle filled to its level: collar and valve on top, a
 * domed body, a foot ring. The fill is the body's own shape clipped to the
 * level, so it follows the domes instead of squaring them off.
 *
 * Drawn from theme tokens, so it reads in both themes.
 */

interface Props {
  /** Percent, 0 to 100. Null before the first reading. */
  level: number | null
  /** The fill's colour, from the tank's own alert lines. */
  tone: TankTone
  /** A word under the level ("Low") once a line is crossed. */
  status?: string | null
  /** What a screen reader hears, e.g. "Level 72%". */
  label: string
  className?: string
}

/** The body, in viewBox units. */
const BODY = { x: 10, y: 34, width: 80, height: 116, radius: 30 }

const FILL_CLASS: Record<TankTone, string> = {
  // `--color-primary` is `var(--accent)`, so this follows the accent setting.
  accent: 'fill-primary',
  warning: 'fill-warning',
  danger: 'fill-danger',
}

export default function TankGraphic({ level, tone, status, label, className }: Props): ReactElement {
  const clipId = `tank-${useId().replace(/:/g, '')}`
  const clamped = level == null ? null : Math.min(100, Math.max(0, level))
  const fillHeight = clamped == null ? 0 : (BODY.height * clamped) / 100
  const bodyShape = {
    x: BODY.x,
    y: BODY.y,
    width: BODY.width,
    height: BODY.height,
    rx: BODY.radius,
  }

  return (
    <svg viewBox="0 0 100 170" role="img" aria-label={label} className={className}>
      <defs>
        <clipPath id={clipId}>
          <rect {...bodyShape} />
        </clipPath>
      </defs>

      {/* Collar with its two hand holes, and the valve under it. */}
      <rect x="26" y="4" width="48" height="26" rx="8" className="fill-surface-2 stroke-text-faint" strokeWidth="2" />
      <rect x="34" y="10" width="12" height="11" rx="4" className="fill-surface stroke-text-faint" strokeWidth="1.5" />
      <rect x="54" y="10" width="12" height="11" rx="4" className="fill-surface stroke-text-faint" strokeWidth="1.5" />
      <rect x="44" y="26" width="12" height="10" rx="2" className="fill-text-faint" />

      {/* Body, fill, weld seam, outline: in that order so the outline stays crisp. */}
      <rect {...bodyShape} className="fill-surface-2" />
      {clamped != null ? (
        <rect
          x={BODY.x}
          y={BODY.y + BODY.height - fillHeight}
          width={BODY.width}
          height={fillHeight}
          clipPath={`url(#${clipId})`}
          className={FILL_CLASS[tone]}
          opacity="0.85"
        />
      ) : null}
      <line
        x1={BODY.x}
        x2={BODY.x + BODY.width}
        y1={BODY.y + BODY.height / 2}
        y2={BODY.y + BODY.height / 2}
        className="stroke-text-faint"
        strokeWidth="1"
        strokeDasharray="3 3"
        opacity="0.5"
      />
      <rect {...bodyShape} fill="none" className="stroke-text-mute" strokeWidth="2.5" />

      {/* Foot ring. */}
      <rect x="22" y="150" width="56" height="16" rx="3" className="fill-surface-2 stroke-text-faint" strokeWidth="2" />

      <text
        x="50"
        y={BODY.y + BODY.height / 2 + 6}
        textAnchor="middle"
        className="fill-text font-mono font-bold"
        fontSize="20"
        aria-hidden="true"
      >
        {clamped == null ? '--' : `${formatAtPrecision(clamped, 0)}%`}
      </text>
      {status ? (
        <text
          x="50"
          y={BODY.y + BODY.height / 2 + 22}
          textAnchor="middle"
          className="fill-text font-semibold uppercase"
          fontSize="11"
          letterSpacing="1"
          aria-hidden="true"
        >
          {status}
        </text>
      ) : null}
    </svg>
  )
}
