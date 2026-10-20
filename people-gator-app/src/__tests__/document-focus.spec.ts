import { describe, expect, it } from 'vitest'
import { focusTransform, MAXIMUM_AUTOMATIC_ZOOM, MINIMUM_ZOOM } from '@/viewmodels/document-focus'

const page = { left: 100, top: -200, width: 540, height: 900 }
const viewer = { width: 800, height: 600, toolbarBottom: 80 }
const current = { scale: 1, x: 0, y: 0 }
describe('document focus geometry', () => {
  it('centers the complete region below the toolbar with context', () => {
    const target = { left: 70, top: 80, width: 20, height: 10 }
    const result = focusTransform(target, page, viewer, current)!
    const cx = page.left + 0.8 * page.width
    const cy = page.top + 0.85 * page.height
    expect(400 + (cx - 400 + result.x) * result.scale).toBeCloseTo(400)
    expect(300 + (cy - 300 + result.y) * result.scale).toBeCloseTo(340)
    expect(90 * result.scale).toBeLessThan(472)
  })
  it('is independent of the existing pan/zoom and page aspect ratio', () => {
    const target = { left: 20, top: 30, width: 40, height: 5 }
    const first = focusTransform(target, page, viewer, current)!
    const scale = 2
    const x = 30,
      y = -70
    const transformed = {
      left: 400 + (page.left - 400 + x) * scale,
      top: 300 + (page.top - 300 + y) * scale,
      width: page.width * scale,
      height: page.height * scale,
    }
    expect(focusTransform(target, transformed, viewer, { scale, x, y })).toEqual(first)
    const wide = focusTransform(target, { ...page, width: 2000, height: 300 }, viewer, current)!
    expect(wide.scale).toBeLessThan(first.scale)
  })
  it('caps tiny targets and uses minimum zoom when a large target cannot fit', () => {
    expect(
      focusTransform({ left: 0, top: 0, width: 0.1, height: 0.1 }, page, viewer, current)?.scale,
    ).toBe(MAXIMUM_AUTOMATIC_ZOOM)
    expect(
      focusTransform(
        { left: 0, top: 0, width: 100, height: 100 },
        { ...page, width: 3000, height: 4000 },
        viewer,
        current,
      )?.scale,
    ).toBe(MINIMUM_ZOOM)
  })
  it('rejects invalid geometry and waits for a usable viewer', () => {
    for (const position of [
      { left: NaN, top: 0, width: 10, height: 10 },
      { left: 95, top: 0, width: 10, height: 10 },
      { left: 0, top: 0, width: 0, height: 10 },
    ])
      expect(focusTransform(position, page, viewer, current)).toBeNull()
    expect(
      focusTransform(
        { left: 0, top: 0, width: 10, height: 10 },
        page,
        { width: 30, height: 50, toolbarBottom: 70 },
        current,
      ),
    ).toBeNull()
  })
})
