import { mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { usePageTableHeader } from '@/composables/page-table-header'

let originTop: number
let scroll: number
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
  originTop = 120
  scroll = 0
  tableHeight = 600
  navBottom = 52
  pending = undefined
  vi.spyOn(window, 'scrollY', 'get').mockImplementation(() => scroll)
  vi.stubGlobal(
    'requestAnimationFrame',
    vi.fn((callback: FrameRequestCallback) => {
      pending = callback
      return 1
    }),
  )
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
      top: this.tagName === 'TABLE' ? originTop - scroll : 0,
      bottom: this.hasAttribute('data-page-navigation')
        ? navBottom
        : originTop - scroll + tableHeight,
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
  const wrapper = mount(
    defineComponent({
      setup() {
        const frame = ref<HTMLElement | null>(null)
        usePageTableHeader(frame)
        return () =>
          h('div', { ref: frame }, [h('table', [h('thead', [h('tr', [h('th', 'Name')])])])])
      },
    }),
  )
  cleanups.push(() => wrapper.unmount())
  return { wrapper, header: wrapper.get('thead').element }
}
it('pins immediately below navigation and releases at the table end', () => {
  const { header } = render()
  expect(header.style.transform).toBe('translate3d(0, 0px, 0)')
  scroll = 320
  window.dispatchEvent(new Event('scroll'))
  expect(header.style.transform).toBe('translate3d(0, 252px, 0)')
  expect(pending).toBeUndefined()
  scroll = 690
  window.dispatchEvent(new Event('scroll'))
  expect(header.style.transform).toBe('translate3d(0, 560px, 0)')
})
it('does not read layout, query the DOM or schedule animation frames while scrolling', () => {
  const { header } = render()
  const bounds = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect')
  const lookup = vi.spyOn(document, 'querySelector')
  const height = vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get')
  bounds.mockClear()
  height.mockClear()
  for (let i = 1; i <= 30; i++) {
    scroll = 120 + i * 10
    window.dispatchEvent(new Event('scroll'))
  }
  expect(header.style.transform).toBe('translate3d(0, 352px, 0)')
  expect(bounds).not.toHaveBeenCalled()
  expect(height).not.toHaveBeenCalled()
  expect(lookup).not.toHaveBeenCalled()
  expect(requestAnimationFrame).not.toHaveBeenCalled()
})
it('remeasures after pagination, ancestor/header/navigation resizing and viewport changes', () => {
  const { header } = render()
  scroll = 690
  tableHeight = 1200
  navBottom = 64
  resized([], {} as ResizeObserver)
  flushFrame()
  expect(header.style.transform).toBe('translate3d(0, 634px, 0)')
  originTop = 900
  window.dispatchEvent(new Event('resize'))
  flushFrame()
  expect(header.style.transform).toBe('translate3d(0, 0px, 0)')
})
it('disconnects observers, listeners and pending measurement on unmount', () => {
  const { wrapper } = render()
  resized([], {} as ResizeObserver)
  expect(pending).toBeDefined()
  wrapper.unmount()
  expect(disconnect).toHaveBeenCalledOnce()
  expect(cancel).toHaveBeenCalledWith(1)
  pending = undefined
  window.dispatchEvent(new Event('scroll'))
  window.dispatchEvent(new Event('resize'))
  expect(pending).toBeUndefined()
})
