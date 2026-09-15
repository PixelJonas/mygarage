/**
 * The backend and the frontend must convert with the same factors.
 *
 * Before v3.4.0 nothing compared them, and the pound drifted: 0.453592 here,
 * 0.45359237 in the backend. The frontend CI job checks out the whole
 * repository, so this reads the backend's constant table directly. Only the
 * BASE factors are parsed; each layer's own tests pin its derived factors to
 * the definitions, so equal bases mean equal derived values.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { UnitConverter } from '../units'

const BACKEND_UNITS = resolve(__dirname, '../../../../backend/app/utils/units.py')

const BASE_FACTORS = [
  'MILES_TO_KM',
  'FEET_TO_METERS',
  'INCH_TO_METERS',
  'US_GALLONS_TO_LITERS',
  'UK_GALLONS_TO_LITERS',
  'LBS_TO_KG',
  'STANDARD_GRAVITY',
] as const

function backendDecimal(source: string, name: string): number {
  const match = source.match(new RegExp(`^\\s+${name} = Decimal\\("([0-9.]+)"\\)`, 'm'))
  if (!match) throw new Error(`${name} not found as a Decimal literal in backend units.py`)
  return Number(match[1])
}

describe('conversion factors agree across the backend and the frontend', () => {
  const source = readFileSync(BACKEND_UNITS, 'utf8')

  it.each(BASE_FACTORS)('%s is the same number in both layers', (name) => {
    expect(UnitConverter[name]).toBe(backendDecimal(source, name))
  })

  it('derives the same pressure, torque and fuel economy factors from those bases', () => {
    const lbf = UnitConverter.LBS_TO_KG * UnitConverter.STANDARD_GRAVITY
    const close = (a: number, b: number): boolean => Math.abs(a - b) <= Math.abs(b) * 1e-12
    expect(close(UnitConverter.LBF_TO_N, lbf)).toBe(true)
    expect(close(UnitConverter.PSI_TO_KPA, lbf / (0.0254 * 0.0254) / 1000)).toBe(true)
    expect(close(UnitConverter.LBFT_TO_NM, lbf * 0.3048)).toBe(true)
    expect(close(UnitConverter.US_MPG_TO_L100KM, (100 * 3.785411784) / 1.609344)).toBe(true)
    expect(close(UnitConverter.UK_MPG_TO_L100KM, (100 * 4.54609) / 1.609344)).toBe(true)
  })
})
