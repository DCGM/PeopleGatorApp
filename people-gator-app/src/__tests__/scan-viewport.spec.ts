import Panzoom from '@panzoom/panzoom'
import { effectScope, nextTick, ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useScanViewport } from '@/composables/scan-viewport'

vi.mock('@panzoom/panzoom', () => ({
  default: vi.fn((_element, options) => {
    let scale = options.startScale
    let position = { x: options.startX, y: options.startY }
    return {
      getScale: () => scale,
      getPan: () => position,
      zoom: vi.fn((value) => {
        scale = value
      }),
      pan: vi.fn((x, y) => {
        position = { x, y }
      }),
      reset: vi.fn(),
      zoomWithWheel: vi.fn(),
      destroy: vi.fn(),
    }
  }),
}))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
  document.body.innerHTML = ''
})

function nodes() {
  const viewer = document.createElement('div')
  const zoom = document.createElement('div')
  const page = document.createElement('div')
  zoom.append(page)
  viewer.append(zoom)
  document.body.append(viewer)
  return { viewer, zoom, page }
}
function setup() {
  const initial = nodes()
  const viewer = ref<HTMLElement | null>(initial.viewer)
  const zoom = ref<HTMLElement | null>(initial.zoom)
  const page = ref<HTMLElement | null>(initial.page)
  const pageKey = ref('page-one')
  const bounds = ref(null)
  const percent = ref(82)
  const resized = vi.fn()
  const scope = effectScope()
  const scan = scope.run(() =>
    useScanViewport(viewer, zoom, page, pageKey, bounds, percent, resized),
  )!
  return { scan, scope, initial, viewer, zoom, page, pageKey, bounds, percent, resized }
}

describe('scan element resource ownership', () => {
  it('rebinds actual replacement, retaining its view, and rejects stale actions and callbacks', async () => {
    const observers: { callback: ResizeObserverCallback; disconnect: ReturnType<typeof vi.fn> }[] =
      []
    vi.stubGlobal(
      'ResizeObserver',
      class {
        disconnect = vi.fn()
        observe = vi.fn()
        constructor(callback: ResizeObserverCallback) {
          observers.push({ callback, disconnect: this.disconnect })
        }
      },
    )
    const state = setup()
    await nextTick()
    const first = state.scan.current()!
    first.zoom(1.8)
    first.pan(12, -34)
    state.initial.viewer.dispatchEvent(new WheelEvent('wheel'))
    expect(first.zoomWithWheel).toHaveBeenCalledTimes(1)
    const replacement = nodes()
    state.viewer.value = replacement.viewer
    state.zoom.value = replacement.zoom
    state.page.value = replacement.page
    // Even before the post-render watcher runs, no action can reach the old instance.
    expect(state.scan.current()).toBeNull()
    await nextTick()
    const second = state.scan.current()!
    expect(second).not.toBe(first)
    expect(first.destroy).toHaveBeenCalledTimes(1)
    expect(observers[0]!.disconnect).toHaveBeenCalledTimes(1)
    expect(second.getScale()).toBe(1.8)
    expect(second.getPan()).toEqual({ x: 12, y: -34 })
    state.initial.viewer.dispatchEvent(new WheelEvent('wheel'))
    expect(first.zoomWithWheel).toHaveBeenCalledTimes(1)
    replacement.viewer.dispatchEvent(new WheelEvent('wheel'))
    expect(second.zoomWithWheel).toHaveBeenCalledTimes(1)
    const resizeCount = state.resized.mock.calls.length
    observers[0]!.callback([], {} as ResizeObserver)
    expect(state.resized).toHaveBeenCalledTimes(resizeCount)
    state.initial.zoom.dispatchEvent(new CustomEvent('panzoomchange', { detail: { scale: 4 } }))
    expect(state.percent.value).toBe(180)
    second.zoom(2)
    replacement.zoom.dispatchEvent(new CustomEvent('panzoomchange', { detail: { scale: 2 } }))
    expect(state.percent.value).toBe(200)
    // A queued Panzoom animation frame from the old binding is inert too.
    const oldOptions = vi.mocked(Panzoom).mock.calls[0]![1]!
    oldOptions.setTransform!(state.initial.zoom, { scale: 4, x: 0, y: 0, isSVG: false })
    expect(state.initial.zoom.style.transform).toBe('')
    state.scope.stop()
    expect(state.scan.current()).toBeNull()
    expect(second.destroy).toHaveBeenCalledTimes(1)
    expect(observers[1]!.disconnect).toHaveBeenCalledTimes(1)
    replacement.viewer.dispatchEvent(new WheelEvent('wheel'))
    window.dispatchEvent(new Event('resize'))
    expect(second.zoomWithWheel).toHaveBeenCalledTimes(1)
    expect(state.resized).toHaveBeenCalledTimes(resizeCount)
  })

  it('ignores stale event values when a replacement reuses the zoom element', async () => {
    const state = setup()
    await nextTick()
    const first = state.scan.current()!
    first.zoom(2)
    const replacementPage = document.createElement('div')
    state.initial.zoom.replaceChildren(replacementPage)
    state.page.value = replacementPage
    await nextTick()
    const second = state.scan.current()!
    expect(second).not.toBe(first)
    state.initial.zoom.dispatchEvent(new CustomEvent('panzoomchange', { detail: { scale: 4 } }))
    expect(state.percent.value).toBe(200)
    state.scope.stop()
  })

  it('handles an absent scan and resets retained state for a different page', async () => {
    const state = setup()
    await nextTick()
    const first = state.scan.current()!
    first.zoom(2)
    state.viewer.value = null
    state.zoom.value = null
    state.page.value = null
    await nextTick()
    expect(state.scan.current()).toBeNull()
    expect(state.bounds.value).toBeNull()
    state.pageKey.value = 'page-two'
    const replacement = nodes()
    state.viewer.value = replacement.viewer
    state.zoom.value = replacement.zoom
    state.page.value = replacement.page
    await nextTick()
    const second = state.scan.current()!
    expect(second.getScale()).toBe(0.82)
    state.scan.reset()
    expect(second.reset).toHaveBeenCalledWith({
      animate: false,
      startScale: 0.82,
      startX: 0,
      startY: 0,
    })
    state.scope.stop()
  })
})
