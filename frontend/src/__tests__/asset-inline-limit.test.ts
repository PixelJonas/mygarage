import { describe, it, expect } from 'vitest'
import { neverInlineFonts } from '../../scripts/asset-inline-limit'

describe('asset inlining', () => {
  it('never inlines a font as a data: URI', () => {
    expect(
      neverInlineFonts(
        '/node_modules/@fontsource-variable/jetbrains-mono/files/jetbrains-mono-cyrillic-ext-wght-normal.woff2',
      ),
    ).toBe(false)
    expect(neverInlineFonts('/src/assets/legacy.woff')).toBe(false)
    expect(neverInlineFonts('/src/assets/Icons.TTF')).toBe(false)
  })

  it('leaves every other asset to the default size rule', () => {
    expect(neverInlineFonts('/src/assets/marker.png')).toBeUndefined()
    expect(neverInlineFonts('/src/assets/logo.svg')).toBeUndefined()
  })
})
