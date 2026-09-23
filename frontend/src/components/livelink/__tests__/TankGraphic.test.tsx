import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

import TankGraphic from '../TankGraphic'

/** The fill is the only rect clipped to the body. */
const fillOf = (container: HTMLElement): SVGRectElement | null =>
  container.querySelector('rect[clip-path]')

/** The body's height in the viewBox; the fill is a share of it. */
const BODY_HEIGHT = 116

describe('TankGraphic', () => {
  it('fills to the level, from the bottom', () => {
    const { container } = render(<TankGraphic level={72} tone="success" label="Level 72%" />)

    const fill = fillOf(container)!
    expect(Number(fill.getAttribute('height'))).toBeCloseTo(BODY_HEIGHT * 0.72)
    expect(screen.getByText('72%')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Level 72%' })).toBeInTheDocument()
  })

  it.each(['success', 'warning', 'danger'] as const)('fills in the %s colour it is given', (tone) => {
    const { container } = render(<TankGraphic level={50} tone={tone} label="level" />)

    expect(fillOf(container)).toHaveClass(`fill-${tone}`)
  })

  it('draws an empty tank before the first reading', () => {
    const { container } = render(<TankGraphic level={null} tone="success" label="Level not reported yet" />)

    expect(fillOf(container)).toBeNull()
    expect(screen.getByText('--')).toBeInTheDocument()
  })

  it('never draws past full or below empty', () => {
    const over = render(<TankGraphic level={104} tone="success" label="level" />)
    expect(Number(fillOf(over.container)!.getAttribute('height'))).toBeCloseTo(BODY_HEIGHT)
    over.unmount()

    const under = render(<TankGraphic level={-3} tone="danger" label="level" />)
    expect(Number(fillOf(under.container)!.getAttribute('height'))).toBe(0)
  })
})
