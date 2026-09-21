/**
 * An info card that is one click-to-edit target AND keeps its own text
 * selectable.
 *
 * ★ WHY THIS IS A COMPONENT AND NOT TWO PROPS AT EACH CALL SITE. It replaces
 * `CardEditOverlay`, a transparent full-card `<button className="absolute
 * inset-0 z-10">` whose own docstring said it "sits above everything". It did:
 * nothing underneath could be long-pressed, so on a phone the VIN could not be
 * selected and the selection handles would not drag (issue #179). The fix needs
 * a container handler AND a keyboard control AND a selection guard, at seven
 * call sites across three files. Wiring three things by hand seven times is how
 * one card ends up with two of them, so the pattern lives here instead.
 *
 * The three pieces:
 *
 * 1. The click handler is on the CARD, not on anything stacked over its
 *    content. Nothing is above the text, so a long-press reaches the text.
 * 2. A click that merely ENDS a text selection does not open the editor.
 *    Without this, selecting the VIN would open an editor every time you let
 *    go, which trades one annoyance for a worse one.
 * 3. A named button, visually hidden until focused, keeps the action reachable
 *    for keyboard and screen-reader users, who cannot use a container's click
 *    handler at all.
 */

import type { ReactNode } from 'react'
import { Card } from '../ui'

/** Positioning context plus the hover/focus cues of a click-to-edit card. */
export const EDITABLE_CARD_CLASS =
  'relative cursor-pointer ui-motion ui-hover-line hover:shadow-card-hover'

/**
 * Whether the user currently has a real text selection on the page.
 *
 * `isCollapsed` alone is not enough: a plain caret placement is a collapsed
 * range, but so is some browsers' idea of an empty selection after a click, and
 * a whitespace-only string is not something anyone meant to select.
 */
function isSelectingText(): boolean {
  const selection = window.getSelection()
  if (selection === null || selection.isCollapsed) return false
  return selection.toString().trim().length > 0
}

interface EditableCardProps {
  /** Accessible name for the edit action, already translated. */
  label: string
  /** Opens the editor. Omit to render an ordinary, non-editable card. */
  onEdit?: () => void
  /** For masonry/column layouts that must not split a card. */
  breakInside?: boolean
  className?: string
  children: ReactNode
}

export default function EditableCard({
  label,
  onEdit,
  breakInside = false,
  className = '',
  children,
}: EditableCardProps) {
  if (!onEdit) {
    return (
      <Card breakInside={breakInside} className={className}>
        {children}
      </Card>
    )
  }

  return (
    <Card
      breakInside={breakInside}
      className={[EDITABLE_CARD_CLASS, className].filter(Boolean).join(' ')}
      onClick={() => {
        if (!isSelectingText()) onEdit()
      }}
    >
      <button
        type="button"
        onClick={(event) => {
          // The card's own handler would fire on the way up and open the editor
          // a second time.
          event.stopPropagation()
          onEdit()
        }}
        className="ui-focus-ring sr-only focus:not-sr-only focus:absolute focus:right-2 focus:top-2 focus:z-10 focus:rounded-lg focus:bg-surface-2 focus:px-2 focus:py-1 focus:text-xs"
      >
        {label}
      </button>
      {children}
    </Card>
  )
}
