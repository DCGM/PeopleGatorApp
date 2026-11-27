import { describe, expect, it } from 'vitest'
import { focusTransform, FOCUS_MARGIN, MINIMUM_ZOOM } from '@/viewmodels/document-focus'

const page = { left: 100, top: -200, width: 540, height: 900 }
const viewer = { width: 800, height: 600, toolbarBottom: 80 }
const current = { scale: 1, x: 0, y: 0 }
type Transform = { scale: number; x: number; y: number }
/** The page bounds after replacing one Panzoom transform with another. */
function shown(bounds: typeof page, from: Transform, to: Transform) {
  const place = (value: number, center: number, before: number, after: number) =>
    center + ((value - center) / from.scale - before + after) * to.scale
  return {
    left: place(bounds.left, viewer.width / 2, from.x, to.x),
    top: place(bounds.top, viewer.height / 2, from.y, to.y),
    width: (bounds.width / from.scale) * to.scale,
    height: (bounds.height / from.scale) * to.scale,
  }
}
/** Viewer pixel edges of a region given in page percentages. */
function edges(position: typeof page, bounds: typeof page) {
  const left = bounds.left + (position.left / 100) * bounds.width
  const top = bounds.top + (position.top / 100) * bounds.height
  return {
    left,
    top,
    right: left + (position.width / 100) * bounds.width,
    bottom: top + (position.height / 100) * bounds.height,
  }
}
describe('document focus geometry', () => {
  it('keeps zoom and position when the region is fully visible', () => {
    // 262-370px across and 250-340px down: clear of the toolbar and every edge.
    const target = { left: 30, top: 50, width: 20, height: 10 }
    expect(focusTransform(target, page, viewer, current)).toEqual(current)
    const zoomed = { scale: 2, x: 30, y: -70 }
    const bounds = { left: 300, top: 100, width: 1080, height: 1800 }
    expect(
      focusTransform({ left: 5, top: 2, width: 20, height: 10 }, bounds, viewer, zoomed),
    ).toEqual(zoomed)
    // Inside the gutter still counts as visible.
    const edge = { left: 0, top: 0, width: 10, height: 10 }
    expect(
      focusTransform(edge, { left: 0, top: 80, width: 800, height: 520 }, viewer, current),
    ).toEqual(current)
  })
  it('pans the shortest distance to a region outside the view, keeping the zoom', () => {
    const scale = 2
    const from = { scale, x: 30, y: -70 }
    const bounds = shown(page, current, from)
    for (const target of [
      { left: 70, top: 80, width: 20, height: 10 },
      { left: 0, top: 0, width: 20, height: 10 },
      { left: 40, top: 95, width: 10, height: 5 },
    ]) {
      const before = edges(target, bounds)
      const result = focusTransform(target, bounds, viewer, from)!
      expect(result.scale).toBe(scale)
      const after = edges(target, shown(bounds, from, result))
      expect(after.left).toBeGreaterThanOrEqual(-0.001)
      expect(after.right).toBeLessThanOrEqual(viewer.width + 0.001)
      expect(after.top).toBeGreaterThanOrEqual(viewer.toolbarBottom - 0.001)
      expect(after.bottom).toBeLessThanOrEqual(viewer.height + 0.001)
      // An axis that moved stops at the gutter on the side it came from.
      if (before.left < 0) expect(after.left).toBeCloseTo(FOCUS_MARGIN)
      if (before.right > viewer.width) expect(after.right).toBeCloseTo(viewer.width - FOCUS_MARGIN)
      if (before.top < viewer.toolbarBottom)
        expect(after.top).toBeCloseTo(viewer.toolbarBottom + FOCUS_MARGIN)
      if (before.bottom > viewer.height)
        expect(after.bottom).toBeCloseTo(viewer.height - FOCUS_MARGIN)
    }
  })
  it('moves only the axis that is out of view', () => {
    // Visible across, hidden under the toolbar.
    const result = focusTransform(
      { left: 30, top: 25, width: 20, height: 5 },
      page,
      viewer,
      current,
    )!
    expect(result).toEqual({ scale: 1, x: 0, y: 79 })
  })
  it('pans, without zooming, to a region that fits the viewer but not its gutters', () => {
    // 770px of an 800px viewer, clipped by 10px on the left.
    const from = { scale: 1.6, x: 0, y: 0 }
    const bounds = { left: -10, top: 200, width: 770, height: 100 }
    const whole = { left: 0, top: 0, width: 100, height: 100 }
    const result = focusTransform(whole, bounds, viewer, from)!
    expect(result.scale).toBe(from.scale)
    expect(result.y).toBe(0)
    const after = edges(whole, shown(bounds, from, result))
    expect(after.left).toBeCloseTo(15)
    expect(after.right).toBeCloseTo(785)
  })
  it('zooms out and centers a region that cannot fit at the current zoom', () => {
    const from = { scale: 3, x: 0, y: 0 }
    const bounds = shown(page, current, from)
    const target = { left: 10, top: 30, width: 80, height: 10 }
    const result = focusTransform(target, bounds, viewer, from)!
    expect(result.scale).toBeLessThan(from.scale)
    expect(result.scale).toBeGreaterThan(MINIMUM_ZOOM)
    const after = edges(target, shown(bounds, from, result))
    expect((after.left + after.right) / 2).toBeCloseTo(400)
    expect((after.top + after.bottom) / 2).toBeCloseTo(340)
    expect(after.left).toBeGreaterThanOrEqual(FOCUS_MARGIN)
    expect(after.right).toBeLessThanOrEqual(viewer.width - FOCUS_MARGIN)
  })
  it('never zooms in, and stops at the minimum zoom for a region too large to fit', () => {
    const tiny = { left: 0, top: 0, width: 0.1, height: 0.1 }
    expect(focusTransform(tiny, page, viewer, current)?.scale).toBe(1)
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
