import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen } from '../../../__tests__/test-utils'
import Input from '../Input'
import Textarea from '../Textarea'

describe('Input', () => {
  it('forwards id, name and placeholder verbatim', () => {
    // e2e pins #odometer_km and input[name="nickname"]; unit tests pin
    // placeholders at Login.test.tsx and elsewhere (G6).
    render(<Input id="odometer_km" name="odometer_km" placeholder="0" />)
    const input = screen.getByPlaceholderText('0')
    expect(input).toHaveAttribute('id', 'odometer_km')
    expect(input).toHaveAttribute('name', 'odometer_km')
  })

  it('keeps the spinbutton role for numeric inputs', () => {
    render(<Input type="number" aria-label="Quantity" />)
    expect(screen.getByRole('spinbutton', { name: 'Quantity' })).toBeInTheDocument()
  })

  it('keeps the textbox role for text inputs', () => {
    render(<Input type="text" aria-label="VIN" />)
    const input = screen.getByRole('textbox', { name: 'VIN' })
    expect(input).toBeInTheDocument()
    expect(input).toHaveAttribute('type', 'text')
  })

  it('applies the mono family when asked', () => {
    render(<Input mono aria-label="Cost" />)
    expect(screen.getByRole('textbox', { name: 'Cost' })).toHaveClass('font-mono')
  })

  it('marks invalid state for assistive tech', () => {
    render(<Input invalid aria-label="Cost" />)
    expect(screen.getByRole('textbox', { name: 'Cost' })).toHaveAttribute('aria-invalid', 'true')
  })

  it('renders a prefix before the control', () => {
    const { container } = render(<Input prefix="$" aria-label="Cost" />)
    expect(container.querySelector('span')).toHaveTextContent('$')
  })

  it('renders a suffix after the control', () => {
    const { container } = render(<Input suffix="kg" aria-label="Weight" />)
    expect(container.querySelector('span')).toHaveTextContent('kg')
    expect(screen.getByRole('textbox', { name: 'Weight' })).toHaveClass('pr-affix')
  })
})

describe('Input: room for its prefix and suffix', () => {
  // jsdom lays nothing out, so each affix's drawn width is stubbed by its text.
  const drawn = (widths: Record<string, number>): void => {
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
      return { width: widths[this.textContent ?? ''] ?? 0 } as DOMRect
    })
  }
  afterEach(() => vi.restoreAllMocks())

  it('pads past a prefix as wide as it is drawn', () => {
    // A fixed pl-7 fits "$" and hid the digits behind "PLN".
    drawn({ PLN: 31 })
    render(<Input prefix="PLN" aria-label="Cost" />)

    const input = screen.getByRole('textbox', { name: 'Cost' })
    expect(input).toHaveClass('pl-affix')
    expect(input.style.getPropertyValue('--affix-start')).toBe('31px')
  })

  it('pads before a suffix likewise', () => {
    drawn({ 'L/100km': 52 })
    render(<Input suffix="L/100km" aria-label="Economy" />)

    expect(screen.getByRole('textbox', { name: 'Economy' }).style.getPropertyValue('--affix-end')).toBe('52px')
  })

  it('measures again when the prefix changes', () => {
    drawn({ $: 8, CHF: 29 })
    const { rerender } = render(<Input prefix="$" aria-label="Cost" />)
    rerender(<Input prefix="CHF" aria-label="Cost" />)

    expect(screen.getByRole('textbox', { name: 'Cost' }).style.getPropertyValue('--affix-start')).toBe('29px')
  })

  it('leaves the width to the stylesheet default until one is drawn', () => {
    render(<Input prefix="$" aria-label="Cost" />)

    expect(screen.getByRole('textbox', { name: 'Cost' }).style.getPropertyValue('--affix-start')).toBe('')
  })

  it("keeps a caller's own style beside the measured width", () => {
    drawn({ $: 8 })
    render(<Input prefix="$" aria-label="Cost" style={{ color: 'red' }} />)

    const input = screen.getByRole('textbox', { name: 'Cost' })
    expect([input.style.color, input.style.getPropertyValue('--affix-start')]).toEqual(['red', '8px'])
  })
})

describe('Textarea', () => {
  it('renders a real textarea and forwards id', () => {
    render(<Textarea id="notes" aria-label="Notes" />)
    expect(screen.getByRole('textbox', { name: 'Notes' }).tagName).toBe('TEXTAREA')
  })
})
