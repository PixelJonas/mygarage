import { useLayoutEffect, useState } from 'react'
import type { CSSProperties } from 'react'

/**
 * The drawn width of an input's prefix or suffix, so the input can pad past it.
 *
 * A fixed `pl-7` fits "$" and hid the digits behind "PLN", "CHF" or "R$": the
 * currency symbol is the user's choice, so its width is not known when the
 * form is written. Measured rather than estimated from the text, so an icon
 * prefix and a late-loading font come out right too.
 *
 * Returns a ref for the affix element and its width in px, or null until it
 * has been drawn (jsdom, or not laid out yet). The input reads the width from
 * `affixStyle` through the `pl-affix` / `pr-affix` utilities; while it is
 * null they use the one-symbol default declared on :root in index.css.
 *
 * @param watch Measure again when this changes (the affix's content).
 */
export function useAffixWidth(watch: unknown): [(el: HTMLElement | null) => void, number | null] {
  const [el, setEl] = useState<HTMLElement | null>(null)
  const [width, setWidth] = useState<number | null>(null)

  useLayoutEffect(() => {
    if (!el) return
    const measure = (): void => {
      const drawn = el.getBoundingClientRect().width
      // Zero is "not laid out", not a real width: leave the fallback in place.
      setWidth(drawn > 0 ? drawn : null)
    }
    measure()
    // A web font that loads after the first paint changes the width.
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [el, watch])

  return [setEl, width]
}

/** The custom properties `pl-affix` and `pr-affix` read. */
export function affixStyle(start: number | null, end: number | null = null): CSSProperties {
  const style: Record<string, string> = {}
  if (start !== null) style['--affix-start'] = `${start}px`
  if (end !== null) style['--affix-end'] = `${end}px`
  return style as CSSProperties
}
