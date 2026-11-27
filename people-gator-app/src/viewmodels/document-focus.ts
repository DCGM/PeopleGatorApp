import type { PageViewportBounds } from './document-workspace.types'

export const MINIMUM_ZOOM = 0.55
export const MAXIMUM_ZOOM = 3.5
export const FOCUS_MARGIN = 24

/**
 * Smallest view change that shows the whole region. Position is in page
 * percentages; page bounds are already transformed viewer pixels.
 *
 * A fully visible region returns the current transform. A region that fits at
 * the current zoom is panned just far enough to clear the gutter. Only a region
 * too large for the viewer is zoomed out and centered. Null means the geometry
 * is not usable yet.
 */
export function focusTransform(
  position: PageViewportBounds,
  page: PageViewportBounds,
  viewer: { width: number; height: number; toolbarBottom: number },
  current: { scale: number; x: number; y: number },
) {
  if (
    ![
      ...Object.values(position),
      ...Object.values(page),
      ...Object.values(viewer),
      ...Object.values(current),
    ].every(Number.isFinite)
  )
    return null
  if (
    position.left < 0 ||
    position.top < 0 ||
    position.width <= 0 ||
    position.height <= 0 ||
    position.left + position.width > 100.01 ||
    position.top + position.height > 100.01 ||
    page.width <= 0 ||
    page.height <= 0 ||
    current.scale <= 0
  )
    return null
  const toolbar = Math.max(0, viewer.toolbarBottom)
  const top = toolbar + FOCUS_MARGIN
  const width = viewer.width - FOCUS_MARGIN * 2
  const height = viewer.height - top - FOCUS_MARGIN
  if (width <= 0 || height <= 0) return null
  // The region as currently shown, in viewer pixels.
  const left = page.left + (position.left / 100) * page.width
  const targetTop = page.top + (position.top / 100) * page.height
  const shownWidth = (position.width / 100) * page.width
  const shownHeight = (position.height / 100) * page.height
  const shiftX = axisShift(left, shownWidth, 0, viewer.width, FOCUS_MARGIN, width)
  const shiftY = axisShift(targetTop, shownHeight, toolbar, viewer.height, top, height)
  if (shiftX !== null && shiftY !== null) {
    // Panzoom translates in unscaled coordinates.
    return {
      scale: current.scale,
      x: current.x + shiftX / current.scale,
      y: current.y + shiftY / current.scale,
    }
  }
  // Too large for the current zoom: zoom out with proportional context and center.
  const targetWidth = shownWidth / current.scale
  const targetHeight = shownHeight / current.scale
  const scale = Math.max(
    MINIMUM_ZOOM,
    Math.min(current.scale, width / (targetWidth * 1.2), height / (targetHeight * 1.2)),
  )
  const centerX = left + shownWidth / 2
  const centerY = targetTop + shownHeight / 2
  // Panzoom translates about the layer's center origin.
  return {
    scale,
    x: current.x - (centerX - viewer.width / 2) / current.scale,
    y:
      current.y -
      (centerY - viewer.height / 2) / current.scale +
      (top + height / 2 - viewer.height / 2) / scale,
  }
}

/**
 * Viewer pixels to move a span along one axis: zero while it is inside the
 * visible range, otherwise the shortest move into the gutter-inset range.
 * Null when the span is longer than the inset range.
 */
function axisShift(
  start: number,
  length: number,
  visibleStart: number,
  visibleEnd: number,
  insetStart: number,
  insetLength: number,
) {
  // Tolerate sub-pixel rounding from measured rectangles.
  if (start >= visibleStart - 0.5 && start + length <= visibleEnd + 0.5) return 0
  if (length > insetLength) return null
  if (start < insetStart) return insetStart - start
  return Math.min(0, insetStart + insetLength - (start + length))
}
