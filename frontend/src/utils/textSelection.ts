/**
 * Telling "the user clicked this" apart from "the user just finished selecting
 * text inside this".
 *
 * Every card in this app that is one big click target has the same problem: to
 * let someone select a VIN, nothing may cover the text, and once nothing covers
 * it the click that ENDS the selection lands on the card and fires its action.
 * A card that navigates away the moment you finish highlighting its VIN is
 * worse than one you cannot highlight at all, so each of those handlers asks
 * this first (issue #179).
 */

/**
 * Whether the user currently has a real text selection on the page.
 *
 * `isCollapsed` alone is not enough. A plain caret placement is a collapsed
 * range, but some browsers also report a collapsed-but-present selection right
 * after an ordinary click, and a whitespace-only string is not something
 * anybody meant to select. So the text itself is checked.
 *
 * @returns true when there is a non-empty selection.
 */
export function isSelectingText(): boolean {
  const selection = window.getSelection()
  if (selection === null || selection.isCollapsed) return false
  return selection.toString().trim().length > 0
}

/**
 * Wrap a click handler so it does nothing while text is selected.
 *
 * @param action What the click should normally do.
 * @returns A handler safe to put on a container whose text must stay selectable.
 */
export function unlessSelectingText(action: () => void): () => void {
  return () => {
    if (!isSelectingText()) action()
  }
}
