/**
 * A money field: a NumberInput with the user's currency symbol in front.
 *
 * The input pads past the symbol at the width it is drawn (`Input`'s prefix
 * handling), so "PLN", "CHF" and "R$" fit as well as "$". Every form used to
 * hand-build this as a relative div, an absolute symbol and a fixed `pl-7`,
 * twenty times over, and the fixed padding hid the digits behind any symbol
 * wider than one character.
 */
import type { ComponentProps, ReactElement } from 'react'
import { NumberInput } from '../ui'
import { useCurrencyPrefix } from '../../hooks/useCurrencyPrefix'

type Props = Omit<ComponentProps<typeof NumberInput>, 'prefix'>

export default function CurrencyInput(props: Props): ReactElement {
  const prefix = useCurrencyPrefix()
  return <NumberInput prefix={prefix} {...props} />
}
