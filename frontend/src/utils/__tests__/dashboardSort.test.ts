/**
 * The sort menu's pick survives a browser that refuses storage (a private
 * window, site data blocked): every access throws there, and a throw must not
 * take the dashboard's sort menu down with it.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { forgetSortPick, readSortPick, rememberSortPick } from '../dashboardSort'

afterEach(() => {
  vi.restoreAllMocks()
  sessionStorage.clear()
})

function blockStorage(): void {
  const refuse = (): never => {
    throw new DOMException('The operation is insecure.', 'SecurityError')
  }
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(refuse)
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(refuse)
  vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(refuse)
}

describe('the sort pick with storage blocked', () => {
  it('reads as no pick', () => {
    blockStorage()
    expect(readSortPick(1)).toBeNull()
  })

  it('remembering one does not throw', () => {
    blockStorage()
    expect(() => rememberSortPick(1, { sort: 'year-new', over: 'name' })).not.toThrow()
  })

  it('forgetting one does not throw', () => {
    blockStorage()
    expect(() => forgetSortPick(1)).not.toThrow()
  })
})

describe('the sort pick', () => {
  it('reads back what was remembered, for that user only', () => {
    rememberSortPick(1, { sort: 'maintenance', over: 'name' })
    expect(readSortPick(1)).toEqual({ sort: 'maintenance', over: 'name' })
    expect(readSortPick(2)).toBeNull()
    forgetSortPick(1)
    expect(readSortPick(1)).toBeNull()
  })

  it('reads JSON null as no pick', () => {
    sessionStorage.setItem('mygarage:dashboard:sortPick:1', 'null')
    expect(readSortPick(1)).toBeNull()
  })
})
