/**
 * Absolutely-positioned currency-symbol prefix for a hand-styled <input>.
 *
 * Only for an input that is not the `Input` primitive: `CurrencyInput` (and
 * `Input`'s `prefix`) handle the symbol and the room for it themselves. Here
 * the caller gives the input the room: `pl-affix`, with `ref` measured by
 * `useAffixWidth` and the width passed through `affixStyle`, because a fixed
 * `pl-7` fits "$" and hid the digits behind "PLN".
 */
import type { Ref } from 'react'
import { useCurrencySymbol } from '../../hooks/useCurrencySymbol'

interface Props {
  /** Override the default Tailwind positioning classes if a form needs custom offsets. */
  className?: string
  /** For `useAffixWidth`, so the input pads past the symbol as drawn. */
  ref?: Ref<HTMLSpanElement>
}

const DEFAULT_CLASS = 'absolute left-3 top-2 text-text-mute'

export default function CurrencyInputPrefix({ className, ref }: Props) {
  const symbol = useCurrencySymbol()
  return (
    <span ref={ref} className={className ?? DEFAULT_CLASS} aria-hidden="true">
      {symbol}
    </span>
  )
}
