import { useMemo } from 'react'
import type { ReactElement } from 'react'
import { useCurrencySymbol } from './useCurrencySymbol'

/**
 * The user's currency symbol as an input prefix (`Input`'s `prefix`).
 *
 * Hidden from screen readers, as the old absolute prefix was: the field's
 * label names the amount. Memoised on the symbol so the input measures its
 * width once per symbol, not on every render.
 */
export function useCurrencyPrefix(): ReactElement {
  const symbol = useCurrencySymbol()
  return useMemo(() => <span aria-hidden="true">{symbol}</span>, [symbol])
}
