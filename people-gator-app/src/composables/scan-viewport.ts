import Panzoom, { type PanzoomObject } from '@panzoom/panzoom'
import { toValue, watch, type MaybeRefOrGetter, type Ref } from 'vue'

import { MAXIMUM_ZOOM, MINIMUM_ZOOM } from '@/viewmodels/document-focus'
import type { PageViewportBounds } from '@/viewmodels/document-workspace.types'

const INITIAL_SCALE = 0.82
export const SCAN_ZOOM_STEP = 0.24

/** Own resources for the current scan nodes, including genuine node replacement. */
export function useScanViewport(
  viewer: Ref<HTMLElement | null>,
  element: Ref<HTMLElement | null>,
  page: Ref<HTMLElement | null>,
  pageKey: MaybeRefOrGetter<string>,
  bounds: Ref<PageViewportBounds | null>,
  zoomPercent: Ref<number>,
  resized: () => void,
) {
  let binding: {
    viewer: HTMLElement
    element: HTMLElement
    page: HTMLElement
    key: string
    controller: PanzoomObject
  } | null = null
  let saved: { key: string; scale: number; x: number; y: number } | null = null

  function current() {
    return binding &&
      binding.viewer === viewer.value &&
      binding.element === element.value &&
      binding.page === page.value
      ? binding.controller
      : null
  }

  function reset() {
    const controller = current()
    if (!controller || !binding) return
    binding.key = toValue(pageKey)
    saved = null
    // A replacement starts at the retained view; Reset always returns to the default.
    controller.reset({ animate: false, startScale: INITIAL_SCALE, startX: 0, startY: 0 })
  }

  watch(
    [viewer, element, page],
    ([viewerNode, zoomNode, pageNode], _, onCleanup) => {
      bounds.value = null
      if (!viewerNode || !zoomNode || !pageNode) return
      const key = toValue(pageKey)
      const state = saved?.key === key ? saved : null
      let active = true
      const controller = Panzoom(zoomNode, {
        canvas: true,
        handleStartEvent: (event) => event.preventDefault(),
        maxScale: MAXIMUM_ZOOM,
        minScale: MINIMUM_ZOOM,
        startScale: state?.scale ?? INITIAL_SCALE,
        startX: state?.x ?? 0,
        startY: state?.y ?? 0,
        step: 0.45,
        // Panzoom queues transform writes; an old instance must not write after cleanup.
        setTransform: (node, { scale, x, y }) => {
          if (active && current() === controller)
            node.style.transform = `scale(${scale}) translate(${x}px, ${y}px)`
        },
      })
      zoomPercent.value = Math.round((state?.scale ?? INITIAL_SCALE) * 100)
      binding = { viewer: viewerNode, element: zoomNode, page: pageNode, key, controller }

      function measure() {
        if (!active || current() !== controller) return
        const outer = viewerNode!.getBoundingClientRect()
        const inner = pageNode!.getBoundingClientRect()
        bounds.value = {
          left: inner.left - outer.left,
          top: inner.top - outer.top,
          width: inner.width,
          height: inner.height,
        }
      }
      function changed() {
        if (!active || current() !== controller) return
        // A queued event from a previous controller can target a reused node.
        zoomPercent.value = Math.round(controller.getScale() * 100)
        measure()
      }
      function resize() {
        measure()
        if (active && current() === controller) resized()
      }
      function wheel(event: WheelEvent) {
        if (active && current() === controller)
          controller.zoomWithWheel(event, { step: SCAN_ZOOM_STEP })
      }
      viewerNode.addEventListener('wheel', wheel, { passive: false })
      zoomNode.addEventListener('panzoomchange', changed)
      window.addEventListener('resize', resize)
      const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize)
      observer?.observe(viewerNode)
      observer?.observe(pageNode)
      resize()

      onCleanup(() => {
        active = false
        saved = { key: binding!.key, scale: controller.getScale(), ...controller.getPan() }
        viewerNode.removeEventListener('wheel', wheel)
        zoomNode.removeEventListener('panzoomchange', changed)
        window.removeEventListener('resize', resize)
        observer?.disconnect()
        controller.destroy()
        binding = null
      })
    },
    { flush: 'post', immediate: true },
  )

  return { current, reset }
}
