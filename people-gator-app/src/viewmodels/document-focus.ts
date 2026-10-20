import type { PageViewportBounds } from './document-workspace.types'

export const MINIMUM_ZOOM = 0.55
export const MAXIMUM_ZOOM = 3.5
// Automatic focus shares the viewer's 350% ceiling; no tiny target can exceed it.
export const MAXIMUM_AUTOMATIC_ZOOM = MAXIMUM_ZOOM
export const FOCUS_MARGIN = 24

/** Position is in page percentages; page bounds are already transformed viewer pixels. */
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
  const top = Math.max(0, viewer.toolbarBottom) + FOCUS_MARGIN
  const width = viewer.width - FOCUS_MARGIN * 2
  const height = viewer.height - top - FOCUS_MARGIN
  if (width <= 0 || height <= 0) return null
  const targetWidth = ((position.width / 100) * page.width) / current.scale
  const targetHeight = ((position.height / 100) * page.height) / current.scale
  // Add proportional context as well as a fixed viewport gutter.
  const scale = Math.max(
    MINIMUM_ZOOM,
    Math.min(MAXIMUM_AUTOMATIC_ZOOM, width / (targetWidth * 1.2), height / (targetHeight * 1.2)),
  )
  const centerX = page.left + ((position.left + position.width / 2) / 100) * page.width
  const centerY = page.top + ((position.top + position.height / 2) / 100) * page.height
  // Panzoom translates in unscaled coordinates about the layer's center origin.
  return {
    scale,
    x: current.x - (centerX - viewer.width / 2) / current.scale,
    y:
      current.y -
      (centerY - viewer.height / 2) / current.scale +
      (top + height / 2 - viewer.height / 2) / scale,
  }
}
