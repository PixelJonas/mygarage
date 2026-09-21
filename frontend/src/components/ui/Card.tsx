import type { ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  padding?: 'none' | 'sm' | 'md'
  /** Hover lift + accent border. Requires onClick; renders a <button>. */
  interactive?: boolean
  /**
   * Click handler. On an `interactive` card this is the <button>'s; on a plain
   * card it is the container's, which keeps the card's own text selectable.
   */
  onClick?: () => void
  /** For masonry/column layouts that must not split a card. */
  breakInside?: boolean
  className?: string
}

const PADDING = {
  none: '',
  sm: 'p-4',
  md: 'p-6',
} as const

/**
 * The layered surface. Replaces the most-repeated string in the codebase —
 * `bg-garage-surface rounded-lg border border-garage-border p-6` appears 21
 * times verbatim and ~108 times with variations.
 *
 * An interactive card is a real <button>, not a div with onClick: the whole
 * vehicle card is clickable per the design, and that has to be reachable by
 * keyboard.
 */
export default function Card({
  children,
  padding = 'md',
  interactive = false,
  onClick,
  breakInside = false,
  className = '',
}: CardProps) {
  const classes = [
    'rounded-card border border-border bg-surface',
    PADDING[padding],
    breakInside ? 'break-inside-avoid' : '',
    interactive ? 'ui-motion ui-hover-line ui-focus-ring hover:shadow-card-hover w-full text-left cursor-pointer' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  if (interactive) {
    return (
      <button type="button" onClick={onClick} className={classes}>
        {children}
      </button>
    )
  }

  // A NON-interactive card may still carry a click handler, and the difference
  // matters: `interactive` wraps the children in a <button>, and text inside a
  // button cannot be long-pressed to select on a phone. The vehicle info cards
  // are click-to-edit and full of values a reader wants to copy (issue #179),
  // so they take this branch and supply their own keyboard route. See
  // `vehicle-detail/EditableCard`.
  return (
    <div className={classes} onClick={onClick}>
      {children}
    </div>
  )
}
