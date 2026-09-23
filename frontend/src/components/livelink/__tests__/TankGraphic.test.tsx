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
    const { container } = render(<TankGraphic level={72} label="Level 72%" />)

    const fill = fillOf(container)!
    expect(Number(fill.getAttribute('height'))).toBeCloseTo(BODY_HEIGHT * 0.72)
    expect(screen.getByText('72%')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Level 72%' })).toBeInTheDocument()
  })

  it.each([
    [72, 'fill-success'],
    [20, 'fill-warning'],
    [5, 'fill-danger'],
  ])('colours %s%% as %s', (level, tone) => {
    const { container } = render(<TankGraphic level={level} label="level" />)

    expect(fillOf(container)).toHaveClass(tone)
  })

  it('draws an empty tank before the first reading', () => {
    const { container } = render(<TankGraphic level={null} label="Level not reported yet" />)

    expect(fillOf(container)).toBeNull()
    expect(screen.getByText('--')).toBeInTheDocument()
  })

  it('never draws past full or below empty', () => {
    const over = render(<TankGraphic level={104} label="level" />)
    expect(Number(fillOf(over.container)!.getAttribute('height'))).toBeCloseTo(BODY_HEIGHT)
    over.unmount()

    const under = render(<TankGraphic level={-3} label="level" />)
    expect(Number(fillOf(under.container)!.getAttribute('height'))).toBe(0)
  })
})
