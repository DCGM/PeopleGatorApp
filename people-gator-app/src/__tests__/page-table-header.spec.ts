import { mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { usePageTableHeader } from '@/composables/page-table-header'

let tableTop: number
let tableHeight: number
let navBottom: number
let pending: FrameRequestCallback | undefined
let resized: ResizeObserverCallback
const disconnect = vi.fn()
const cancel = vi.fn()
const cleanups: (() => void)[] = []
function flushFrame() {
  const callback = pending
  pending = undefined
  callback?.(0)
}
beforeEach(() => {
  tableTop = 120
  tableHeight = 600
  navBottom = 52
  pending = undefined
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    pending = callback
    return 1
  })
  vi.stubGlobal('cancelAnimationFrame', cancel)
  vi.stubGlobal(
    'ResizeObserver',
    class {
      constructor(callback: ResizeObserverCallback) {
        resized = callback
      }
      observe() {}
      disconnect = disconnect
    },
  )
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (
    this: HTMLElement,
  ) {
    return {
      top: this.tagName === 'TABLE' ? tableTop : 0,
      bottom: this.hasAttribute('data-page-navigation') ? navBottom : tableTop + tableHeight,
      height: tableHeight,
    } as DOMRect
  })
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockReturnValue(40)
  const nav = document.createElement('nav')
  nav.setAttribute('data-page-navigation', '')
  document.body.append(nav)
  cleanups.push(() => nav.remove())
})
afterEach(() => {
  cleanups
    .splice(0)
    .reverse()
    .forEach((cleanup) => cleanup())
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})
function render() {
  let offset!: ReturnType<typeof usePageTableHeader>
  const wrapper = mount(
    defineComponent({
      setup() {
        const frame = ref<HTMLElement | null>(null)
        offset = usePageTableHeader(frame)
        return () =>
          h('div', { ref: frame }, [h('table', [h('thead', [h('tr', [h('th', 'Name')])])])])
      },
    }),
  )
  cleanups.push(() => wrapper.unmount())
  return { wrapper, offset }
}
it('pins below page navigation and releases at the table end', () => {
  const { offset } = render()
  expect(offset.value).toBe(0)
  tableTop = -200
  window.dispatchEvent(new Event('scroll'))
  flushFrame()
  expect(tableTop + offset.value).toBe(navBottom)
  tableTop = -570
  window.dispatchEvent(new Event('scroll'))
  flushFrame()
  expect(offset.value).toBe(560)
  expect(tableTop + offset.value + 40).toBe(tableTop + tableHeight)
})
it('recalculates after pagination, header/navigation resizing and viewport changes', () => {
  const { offset } = render()
  tableTop = -570
  tableHeight = 1200
  navBottom = 64
  resized([], {} as ResizeObserver)
  flushFrame()
  expect(tableTop + offset.value).toBe(64)
  tableTop = 200
  window.dispatchEvent(new Event('resize'))
  flushFrame()
  expect(offset.value).toBe(0)
})
it('disconnects observers, listeners and a pending animation on unmount', () => {
  const { wrapper } = render()
  window.dispatchEvent(new Event('scroll'))
  expect(pending).toBeDefined()
  wrapper.unmount()
  expect(disconnect).toHaveBeenCalledOnce()
  expect(cancel).toHaveBeenCalledWith(1)
  pending = undefined
  window.dispatchEvent(new Event('scroll'))
  expect(pending).toBeUndefined()
})
